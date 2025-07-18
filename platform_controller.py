import json
import logging
import os
import pprint
import sys

import IMatchAPI as im
from imatch_image import IMatchImage
import config
from album import Album

class PlatformController():

    def __init__(self, platform_name, preferred_format, allowed_formats) -> None:
        self.name = platform_name
        self.preferred_format = preferred_format
        self.allowed_formats = allowed_formats

        self.images = set()
        self.images_to_add = set()
        self.images_to_delete = set()
        self.images_to_update = set()
        self.invalid_images = set()
        self.albums = {}
        self.image_references = None #List of images referenced in vault .md files
        self.api = None  # Holds the platform api connection once active
        self.testing = im.IMatchAPI.get_application_variable("imatch_to_socials_testing") == 1  # = 0 live, 1 = testing

        self.albums = Album.load(self.name)

        data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),'data.json')

        ## Load all important locations
        try:
            with open(data_file, "r") as file:
                data = json.load(file)

                self.locations = data['locations']
        except json.decoder.JSONDecodeError as e:
            logging.error(f"{self.name}: Unexpected error loading json file : {data_file}")
            logging.error(f"{self.name}: {e}")
            sys.exit(1)
        except FileNotFoundError:
            logging.error(f"{self.name}: Unable to create locations. JSON file not found: {data_file}")
            sys.exit(1)
        except KeyError:
            logging.error(f"{self.name}: Unable to create locations. Data missing from: {data_file}")
            sys.exit(1)

    def __repr__(self):
        return f'{self.name} with {len(self.images)} and {len(self.albums)}.'
    
    def connect(self):
        """Upload and add image to platform"""
        raise NotImplementedError("Subclasses must implement this for their specific platform.")

    def register_image(self, image):
        """Register image to the list of controller's images, and connect to image"""
        image.controller = self
        self.images.add(image)
     
    def add_images(self):
        """Upload and add image to platform"""
        if len(self.images_to_add) == 0:
            return  # Nothing to see here
        
        if not self.testing:        
            self.connect()

        progress_counter = 1
        progress_end = len(self.images_to_add)
        padding = len(str(progress_end))
        for image in self.images_to_add:

            # Upload the media, then the status with the media attached. 
            if self.testing:
                print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] **TEST** Adding {image.name} ({image.size/config.MB_SIZE:2.1f} MB) "{image.title}"')
                progress_counter += 1       
                continue                            
            print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] Adding {image.name} ({image.size/config.MB_SIZE:2.1f} MB) "{image.title}"')

            self.commit_add(image)
            progress_counter += 1

    def classify_images(self):
        print( f'{self.name}: Classifying images.')
        for image in self.images:
            match image.operation:
                case IMatchImage.OP_ADD:
                    self.images_to_add.add(image)
                case IMatchImage.OP_UPDATE:
                    self.images_to_update.add(image)
                case IMatchImage.OP_METADATA:  # Update process restricts to metadata only
                    self.images_to_update.add(image)
                case IMatchImage.OP_DELETE:
                    self.images_to_delete.add(image)
                case IMatchImage.OP_INVALID:
                    self.invalid_images.add(image)
                case other:
                    pass

    def commit_add(self, image):
        """Make the api call to commit the image to the platform, and update IMatch with reference details"""
        raise NotImplementedError("Subclasses must implement this for their specific platform.")

    def commit_delete(self, image):
        """Make the api call to delete the image from the platform"""
        raise NotImplementedError("Subclasses must implement this for their specific platform.")
    
    def commit_update(self, image):
        """Make the api call to update the image on the platform"""
        raise NotImplementedError("Subclasses must implement this for their specific platform.")

    def delete_images(self):
        """Delete images from the platform"""
        if len(self.images_to_delete) == 0:
            return  # Nothing to see here
        
        if not self.testing:
            self.connect()

        deleted_images = set()
        progress_counter = 1
        progress_end = len(self.images_to_delete)
        padding = len(str(progress_end))
        for image in self.images_to_delete:
            if self.testing:
                print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] **Test** Deleting "{image.title}"')
                progress_counter += 1       
                continue    
            print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] Deleting "{image.title}"  ... {image.name}')

            self.commit_delete(image)
            deleted_images.add(image.id)
            progress_counter += 1       

        # Unassign all deleted images from the deleted category
        im.IMatchAPI.unassign_category(
            im.IMatchUtility.build_category([
                config.ROOT_CATEGORY,
                self.name,
                config.DELETE_CATEGORY
                ]), 
            list(deleted_images)
            )
        im.IMatchAPI.delete_attributes(self.name,list(deleted_images))

    def get_album(self, name):
        try:
            return self.albums[name]
        except KeyError:
            return None

    def process_errors(self):
        """List information about all images that are invalid and were not processed"""
        # Clear all images from the error categories before assigning those from this run.
        children = im.IMatchAPI().get_categories_children("|".join([config.ROOT_CATEGORY,self.name,config.ERROR_CATEGORY]))
        for child in children:
            if len(child['files']) > 0:
                im.IMatchAPI().unassign_category(child['path'], child['files'])

        if len(self.invalid_images) > 0:

            print( "--------------------------------------------------------------------------------------")
            print(f"{self.name}: Images with errors detected and assigned to '{config.ROOT_CATEGORY}|{self.name}' error categories.")
            for image in sorted(self.invalid_images, key=lambda x: x.name):
                for error in image.errors:
                    im.IMatchAPI().assign_category("|".join([config.ROOT_CATEGORY,self.name,config.ERROR_CATEGORY,error]), image.id)

    def finalise(self):
        self.process_errors()

    def summarise(self):
        """Output summary of images processed"""
        stats = self.stats
        print( "--------------------------------------------------------------------------------------")
        print(f"{self.name}: Summary of images processed")
        for val in stats.keys():
            print(f"-- {stats[val]} {val} images")

    def update_images(self):
        """Update images already on the platform"""
        if len(self.images_to_update) == 0:
            return  # Nothing to see here
        
        if not self.testing:
            self.connect()

        progress_counter = 1
        progress_end = len(self.images_to_update)
        padding = len(str(progress_end))
        for image in self.images_to_update:

            if image.operation == IMatchImage.OP_UPDATE:
                action = "all"
            else:
                action = "metadata"
        
            
            if self.testing:
                print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] **TEST** Updating {action} for {image.name} ({image.size/config.MB_SIZE:2.1f} MB) "{image.title}"')
                progress_counter += 1       
                continue
            print(f'{self.name}: [{progress_counter:0{padding}}/{progress_end:0{padding}}] Updating {action} for {image.name} ({image.size/config.MB_SIZE:2.1f} MB) "{image.title}"')

            self.commit_update(image)

            if image.operation == IMatchImage.OP_UPDATE:
                im.IMatchAPI.unassign_category(
                    im.IMatchUtility.build_category([
                        config.ROOT_CATEGORY,
                        self.name,
                        config.UPDATE_CATEGORY
                        ]), 
                    image.id
                    )

            if image.operation == IMatchImage.OP_METADATA:
                im.IMatchAPI.unassign_category(
                    im.IMatchUtility.build_category([
                        config.ROOT_CATEGORY,
                        self.name,
                        config.UPDATE_METADATA_CATEGORY
                        ]), 
                    image.id
                    )
                

            progress_counter += 1       

    @property
    def stats(self):
        return {
            "total" : len(self.images),
            "added" : len(self.images_to_add),
            "deleted" : len(self.images_to_delete),
            "updated" : len(self.images_to_update),
            "invalid" : len(self.invalid_images),
            "untouched" : len(self.images)
                        - len(self.images_to_add)
                        - len(self.images_to_delete)
                        - len(self.images_to_update)
                        - len(self.invalid_images)
        }