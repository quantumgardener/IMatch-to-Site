from datetime import datetime
from pprint import pformat, pprint
import os
import shutil
import sys
import logging

import flickrapi

from imatch_image import IMatchImage
import IMatchAPI as im
from platform_controller import PlatformController
from album import Album
import config
from utilities import print_clear, replace_extension, set_metadata

logging.getLogger("flickrapi.core").setLevel(logging.CRITICAL)  # Hide basic info messages from flickr api

class FlickrImage(IMatchImage):

    __MAX_SIZE = 200 * config.MB_SIZE

    def __init__(self, id, platform) -> None:
        super().__init__(id, platform)
        self.groups = set()

        if self.size > FlickrImage.__MAX_SIZE:
            logging.warning(f'{self.name}: {self.filename} may be too large to upload: {self.size/config.MB_SIZE:>6.2f} MB. Max is {FlickrImage.__MAX_SIZE/config.MB_SIZE:>6.2f} MB.')

    def _prepare_for_operations(self) -> None:
        """Build variables ready for uploading."""
        super()._prepare_for_operations()

        #Set up the text items
        tmp_description = []

        if self.headline != "":
            tmp_description.append(self.headline)
            tmp_description.append('')

        if hasattr(self, 'description'):
            if self.description != "":
                tmp_description.append(self.description)
                tmp_description.append('')

        if hasattr(self, 'ai_description'):
            if self.ai_description != "":
                tmp_description.append(self.ai_description)
                tmp_description.append('')

        if self.circadatecreated != "":
            tmp_description.append(f"Taken ca. {self.date_time.strftime("%#d %B %Y")}.")
            tmp_description.append('')

        for category in self.categories:
            splits = category['path'].split("|")
            match splits[0]:
                case "Socials":
                    if splits[1] == "flickr":
                        # Need to grab any albums and groups
                        try:
                            if splits[2] == "albums":
                                # Code is in the description
                                self.albums.append(category['description'])
                            if splits[2] == "groups":
                                # Code is in the description due to the presence of @ being illegal in the name
                                self.groups.append(category['description'])
                        except IndexError:
                            pass #no groups or albums found

        shooting_info = self.shooting_info
        if shooting_info != '':
            tmp_description.append(shooting_info)
        
        camera_info = self.camera_info
        if camera_info != '':
            tmp_description.append(camera_info)

        self.description = "\n".join(tmp_description)
        return None
    
    @property
    def is_valid(self) -> bool:
        result = super().is_valid
        for attribute in []:
            try:
                if getattr(self, attribute).strip() == '':
                    self.errors.append(f"missing {attribute}")
            except AttributeError:
                self.errors.append(f"missing {attribute}")
        if self.size > FlickrImage.__MAX_SIZE:
            self.errors.append(f"file too large")
        return len(self.errors) == 0 and result

    @property
    def is_on_platform(self) -> bool:
        res = im.IMatchAPI.get_attributes("flickr", self.id)
        return len(res) != 0
    
class FlickrController(PlatformController):

    def __init__(self, platform_name, album_cls, preferred_format, allowed_formats) -> None:
        super().__init__(platform_name, album_cls, preferred_format, allowed_formats)
        self.privacy = config.flickr_secrets['privacy']
        self.upload_format = im.IMatchAPI.FORMAT_JPEG

        logging.debug(f'{self.name}: Instance initialised.')

    
    def add_images(self):
        # Images loaded from raw jpegs will have private location information in them
        # We need to split them out and remove that code with exiftool before the
        # upload. The best way to do this is to avoid uploading originals.
        # 1. Copy to a temp location and point the filename at this file
        # 2. Run exiftool over the files
        # 3. Upload the temp files

        exiftool_tasks = []
        for image in self.images_to_add:
            output_file = replace_extension(os.path.join(config.flickr_secrets['tmp_path'], image.name),"jpg")
            exiftool_tasks.append([image.filename, output_file, image.isPrivate])
            image.filename = output_file

        print(f'{self.name}: Generating images safe to upload')
        for task in exiftool_tasks:
            shutil.copy(task[0], task[1])
        set_metadata(exiftool_tasks)

        super().add_images()

    def classify_images(self):
        super().classify_images()
        for image in self.images:
            if image.operation != IMatchImage.OP_INVALID:
                for category in image.categories:
                    splits = category['path'].split("|")
                    match splits[0]:
                        case "Socials":
                            if splits[1] == "albums":
                                try:
                                    name = splits[2]
                                    try:
                                        self.albums[name].add(image)
                                        logging.debug(f'{self.name}: Adding image to album {name}')
                                    except KeyError:
                                        logging.error(f'{self.name}: Missing album configuration for "{name}". Check secrets.json')
                                        sys.exit(1)
                                except IndexError:
                                    pass #no albums found

    def connect(self):
        if self.api is not None:
            return
        else: 
            try:
                print(f"{self.name}: Work to do -- Connecting to platform.")
                flickr = flickrapi.FlickrAPI(
                    config.flickr_secrets["api_key"],
                    config.flickr_secrets["api_secret"],
                    cache=True
                    )
                flickr.authenticate_via_browser(
                    perms = 'delete'
                    )
                print(f"{self.name}: Authenticated.")
            except Exception as ex:
                logging.error(f"{self.name}: {ex}")
                sys.exit()
            
            self.api = flickr


    def commit_add(self, image):       
        """Make the api call to commit the image to the platform, and update IMatch with reference details"""
        try:
            logging.debug("[commit_add] Image variables\n%s:", pformat(image.__dict__))
            response = self.api.upload(
                image.filename,
                title = image.title if image.title != '' else image.name,
                description = image.description,
                is_public = self.privacy['is_public'],
                is_friend = self.privacy['is_friend'],
                is_family = self.privacy['is_family'],
                )
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to upload image to flickr")
        except flickrapi.FlickrError as fe:
            print_clear()
            logging.error(f"Error adding file: {fe}")
            sys.exit(1)

        photo_id = response.findtext('photoid')
            
        try:
            # Force date. Sometimes exif date does not pull through, especially for scans
            logging.debug(f"[commit_add] Setting date for {image.filename}")
            response = self.api.photos.setDates(
                photo_id=photo_id, 
                date_taken=str(image.date_time), 
                date_taken_granularity=0
                )
            if response.attrib['stat'] != "ok":
                raise RuntimeError(f"Unable to set date for {image.filename}")
        except flickrapi.FlickrError as fe:
            print_clear()
            logging.error(f"Unable to set date for {image.filename}")
            logging.erorr(fe)
            sys.exit(1)

        for album in image.albums:
            logging.debug(f"[commit_add] Adding {photo_id} to album: {album}")
            try:
                response = self.api.photosets_addPhoto(
                    photoset_id=album.photoset_id, 
                    photo_id=photo_id
                    )
                if response.attrib['stat'] != "ok":
                    raise RuntimeError(f"Unable to add {image.filename} to album: {album.name}, id: {album.photoset_id}")
            except flickrapi.FlickrError as fe:
                print_clear()
                logging.error(f"Unable to add {image.filename} to album: {album.name}, id: {album.photoset_id}")
                logging.error(fe)
                sys.exit(1)

            for group in image.groups:
                response = self.api.groups_pools_add(group_id=group, photo_id=photo_id)

        try:
            # flickr will bring in hierarchical keywords not under our control as level|level|level
            # which frankly is stupid. Easiest way is to delete them all. We don't know quite what
            # it will have loaded.
            logging.debug("[commit_add] Pulling down image tag info")
            response = self.api.photos.getInfo(
                photo_id = photo_id,
                format="parsed-json"
                )
            if response['stat'] != "ok":
                raise RuntimeError(f"Error accessing getInfo")
            logging.debug("[commit_add] Image tag info\n%s:", pformat(response['photo']['tags']))

            for tag in response['photo']['tags']['tag']:
                for keyword in image.hierarchical_keywords:
                    if tag['raw'] == keyword:
                        logging.debug(f"[commit_add] Removing tag {tag['id']}")
                        response = self.api.photos.removeTag(tag_id=tag['id'])               
                        if response.attrib['stat'] != "ok":
                            raise RuntimeError(f"Error removing tag {tag['id']}")
            
            # Now add back the "Approved" tags. If added on upload, they combine with IPTC weirdly
            response = self.api.photos.addTags(
                tags=",".join(image.flat_keywords), 
                photo_id=photo_id)
            if response.attrib['stat'] != "ok":
                raise RuntimeError(f"Error adding tags {image.flat_keywords}")
        except flickrapi.FlickrError as fe:
                logging.error(fe)
                sys.exit(1)

        # Update the image in IMatch by adding the attributes below.
        posted = datetime.now().isoformat()[:10]
        im.IMatchAPI.set_attributes(self.name, image.id, data = {
            'posted' : posted,
            'photo_id' : photo_id,
            'url' : f"{config.flickr_secrets["url"]}{photo_id}"
            })

                            
    def commit_delete(self, image):
        """Make the api call to delete the image from the platform
        If it has been favourited, or commented, do not delete"""

        # Ok to assume image has attributes. If it did not it would not pass the earlier tests to be in the list
        # of deletion candidates.
        attributes = im.IMatchAPI().get_attributes(self.name, image.id)[0]
        photo_id = attributes['photo_id']

        try:    
            logging.debug(f"[commit_delete] Checking for comments {image.name}, {photo_id}")
            response = self.api.photos.getInfo(
                photo_id = photo_id,
                format="parsed-json"
                )
            if response['stat'] != "ok":
                raise RuntimeError(f"[commit_delete] Unable to check for comments {image.name}, {photo_id}")
        except flickrapi.FlickrError as fe:
            logging.error(f"[commit_delete] Unable to check for comments {image.name}, {photo_id}")
            logging.error(fe)
            logging.error(response)
            sys.exit(1)
 
        if response['photo']['comments']['_content'] != '0':
            # Commented image, do not delete
            image.errors.append("commented file")
            self.invalid_images.add(image)
            return False

        try:    
            logging.debug(f"[commit_delete] Checking for faves {image.name}, {photo_id}")
            response = self.api.photos.getFavorites(
                photo_id = photo_id,
                format="parsed-json"
                )
            if response['stat'] != "ok":
                raise RuntimeError(f"[commit_delete] Unable to check for faves {image.name}, {photo_id}")
        except flickrapi.FlickrError as fe:
            logging.error(f"[commit_delete] Unable to check for faves {image.name}, {photo_id}")
            logging.error(fe)
            logging.error(response)
            sys.exit(1)

        if bool(response.get("photo", {}).get("person")):
            # Favorited, do not delete
            image.errors.append("faved file")
            self.controller.invalid_images.add(image)
            return False

        try:    
            logging.debug(f"[commit_delete] Deleting {image.name}, {photo_id}")
            response = self.api.photos.delete(photo_id = photo_id)
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to delete image")
        except flickrapi.FlickrError as fe:
            logging.error(fe)
            logging.error(response)
            sys.exit(1)

        try:
            output_file = replace_extension(os.path.join(config.flickr_secrets['tmp_path'], image.name),"jpg")
            os.remove(output_file)
        except:
            # Temp folder, don't really care if it fails
            pass

        return True

    def commit_update(self, image):
        """Make the api call to update the image on the platform"""
        try:
            attributes = im.IMatchAPI().get_attributes(self.name, image.id)[0]
            photo_id = attributes['photo_id']

            # Some manually added photos don't have a posted date, so pull it down if needed
            # if 'posted' not in attributes:
            #     response = self.api.photos.getInfo(photo_id = photo_id, format = "parsed-json")
            #     posted = datetime.fromtimestamp(int(response['photo']['dates']['posted']))
            #     im.IMatchAPI.set_attributes(self.name, image.id, data = {
            #         'posted' : str(posted)[:10],
            #         'photo_id' : photo_id,
            #         'url' : f"{config.flickr_secrets["url"]}{photo_id}"
            #         })
                    
            logging.debug(f"[commit_update] Set title and description for {photo_id}")
            response = self.api.photos.setMeta(
                title = image.title if image.title != '' else image.name,
                description = image.description,  
                photo_id = photo_id
                )  
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to update title and description")

            if image.operation == IMatchImage.OP_UPDATE:
                # Update image alongside metadata
                logging.debug(f"[commit_update] Replacing image for {photo_id}")
                response = self.api.replace(
                    filename = image.filename, 
                    photo_id = photo_id
                    )
                if response.attrib['stat'] != "ok":
                    raise RuntimeError("Unable to replace image file")

            logging.debug(f"[commit_update] Setting dates for {photo_id}")
            response = self.api.photos.setDates(
                photo_id=photo_id, 
                date_taken=str(image.date_time), 
                date_taken_granularity=0,
                )
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to update date")
            
            logging.debug(f"[commit_update] Resetting tags for {photo_id}")
            ## Get list of assigned tags in flickr
            response = self.api.photos.getInfo(
                photo_id = photo_id, 
                format = "parsed-json")
            logging.debug("[commit_update] Assigned tags\n%s:", pformat(response['photo']['tags']))
            for tag in response['photo']['tags']['tag']:
                if tag['raw'] not in image.flat_keywords:
                    # Don't want this tag anymore, remove it
                    logging.debug(f"[commit_update] Removing tag: {tag['raw']}")
                    response = self.api.photos.removeTag(
                        tag_id=tag['id']) 
                    if response.attrib['stat'] != "ok":
                        raise RuntimeError(f"Unable to remove tag {tag['raw']}")

            response = self.api.photos.addTags(
                tags=",".join(image.flat_keywords), 
                photo_id=photo_id
                )
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to add keywords")

            logging.debug(f"[commit_update] Setting permissions for {photo_id}")
            response = self.api.photos.setPerms(
                photo_id=photo_id,
                is_public=self.privacy['is_public'],
                is_friend= self.privacy['is_friend'],
                is_family = self.privacy['is_family']
            )
            if response.attrib['stat'] != "ok":
                raise RuntimeError("Unable to set permissions")

            logging.debug(f"[commit_update] Requesting contexts for {photo_id}")
            contexts = self.api.photos.getAllContexts(
                photo_id = photo_id,
                format="parsed-json"
                )
            if contexts['stat'] != "ok":
                raise RuntimeError("Unable to get contexts (sets and groups)")


            album_ids = {album.photoset_id for album in image.albums}

            ## Remove the image from any flickr photosets that it should not belong to
            try:
                logging.debug("[commit_update] Contexts (set)\n%s:", pformat(contexts['set']))
                for flickr_album in contexts['set']:
                    # Check if any album in image.albums has a matching photoset_id
                    if flickr_album['id'] not in album_ids:
                        # Flickr says this image is in the album, but IMatch disagrees
                        logging.debug(f"[commit_update] Removing image from `{flickr_album['title']}`")
                        response = self.api.photosets_removePhoto(
                            photoset_id=flickr_album['id'],
                            photo_id=photo_id
                        )
                        if response.attrib['stat'] != "ok":
                            raise RuntimeError(f"Unable to remove image from `{flickr_album['title']}`")
            except KeyError:
                # No set information returned so not in any flickr albums
                logging.debug("[commit_update] Not in any photosets. No action required.")
                pass

            ## Add to any albums it is missing from
            for album in image.albums:
                if "set" in contexts:
                    flickr_albums = {ps['id'] for ps in contexts['set']}
                    if album.photoset_id not in flickr_albums:
                        logging.debug(f"[commit_update] Adding to '{album.name}'")
                        response = self.api.photosets_addPhoto(
                            photoset_id = album.photoset_id,
                            photo_id = photo_id
                            ) 
                        if response.attrib['stat'] != "ok":
                            raise RuntimeError(f"Unable to add to album '{album.name}")
                else:
                    logging.debug(f"[commit_update] Adding to '{album.name}'")
                    response = self.api.photosets_addPhoto(
                        photoset_id = album.photoset_id,
                        photo_id = photo_id
                        ) 
                    if response.attrib['stat'] != "ok":
                        raise RuntimeError(f"Unable to add to album '{album.name}")
            # try:
            #     for flickr_group in contexts['pool']:
            #         # Is the image in the album flickr thinks its in
            #         match = list(filter(lambda group: group == flickr_group['id'], image.groups))
            #         if len(match) == 0:
            #             # Flickr says this image is in the group (pool). IMatch doesn't think it should be
            #             response = self.api.groups_pools_remove(
            #                 group_id=flickr_group['id'],
            #                 photo_id=photo_id
            #                 )
            # except KeyError:
            #     # No pool information returned so not in any flickr groups
            #     pass

            # for group in image.groups:
            #     if "pool" in contexts:
            #         match = list(filter(lambda set: set['id'] == group, contexts['pool']))
            #         if len(match) == 0:
            #             response = self.api.groups_pools_add(
            #                 group_id = group, 
            #                 photo_id=photo_id
            #                 )        
            #     else:
            #         # No groups set, can go ahead and add
            #         response = self.api.groups_pools_add(
            #             group_id = group, 
            #             photo_id=photo_id
            #             )   

            # Update the image in IMatch by adding the attributes below.
            posted = datetime.now().isoformat()[:10]
            im.IMatchAPI.set_attributes(self.name, image.id, data = {
                'posted' : posted,
                'photo_id' : photo_id,
                'url' : f"{config.flickr_secrets["url"]}{photo_id}"
                })
            
        except flickrapi.FlickrError as fe:
            logging.error(fe)
            logging.error(response)
            sys.exit(1)

    def finalise(self):
        if len(self.images_to_add) + len(self.images_to_delete) + len(self.images_to_update) != 0:
            
            
            ## Set album order based on alphabetical album order
            print_clear(f'{self.name}: Finalising -- set album order', end='\r')
            logging.debug(f"[commit_update] Finalising -- set album order")
            sorted_ids = [album.photoset_id for album in sorted(self.albums.values(), key=lambda a: a.name)]
            
            self.connect() 
            try:
                response = self.api.photosets_orderSets(
                    photoset_ids = ",".join(sorted_ids)
                    ) 
                if response.attrib['stat'] != "ok":
                    raise RuntimeError(f"Unable to set album sort order")
            except flickrapi.FlickrError as fe:
                print_clear()
                logging.error(f"Unable to set album sort order")
                logging.error(fe)
                sys.exit(1)

            print_clear(f'{self.name}: Finalising -- updating album metadata', end='\r')
            ## Now, set the thumbnail each album, based off the thumbnail set in the iMatch category and update the name and description
            for album in self.albums.values():
                category_info = im.IMatchAPI.get_category_info(
                    im.IMatchUtility.build_category([
                        config.ROOT_CATEGORY,
                        "albums",
                        album.name
                        ]),
                    params={
                        "fields" : "thumbnail"
                        }
                    )[0]
                if category_info['thumbnail'] != 0:
                    # A thumbnail has been set in IMatch, so make sure flickr album matches
                    response = im.IMatchAPI.get_attributes("flickr", category_info['thumbnail'])
                    if len(response) != 0:
                        # image is on flickr so we can update the thumbnail safely
                        try:
                            response = self.api.photosets_setPrimaryPhoto(
                                photoset_id = album.photoset_id,
                                photo_id = response[0]['photo_id']
                                ) 
                            if response.attrib['stat'] != "ok":
                                raise RuntimeError(f"Unable to set album thumbnail for {album.name}")
                        except flickrapi.FlickrError as fe:
                            print_clear()
                            logging.error(f"Unable to set album thumbnail for {album.name}")
                            logging.error(fe)
                            sys.exit(1)
                # Confirm name and description
                try:
                    response = self.api.photosets_editMeta(
                        photoset_id = album.photoset_id,
                        title = album.name,
                        description = album.description
                        ) 
                    if response.attrib['stat'] != "ok":
                        raise RuntimeError(f"Unable to set title and description for {album.name}")
                except flickrapi.FlickrError as fe:
                    print_clear()
                    logging.error(f"Unable to set title and description for {album.name}")
                    logging.error(fe)
                    sys.exit(1)

        super().finalise()  
        print_clear(f'{self.name}: Finalised')

class FlickrAlbum(Album):
    def __init__(self, name, description, photoset_id):
            
        super().__init__(name, description)
        self.photoset_id = photoset_id

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.name} (photoset_id: {self.photoset_id} images:{len(self.images)}), {self.description} '
    
    def __hash__(self):
        return hash((self.photoset_id, self.name)) 

    @classmethod
    def load(cls):
        albums = {}
        for album in config.albums:
            try:
                albums[album['name']] = cls(album['name'], album['description'], album['photoset_id'])
            except KeyError:
                # If any required fields are missing for the album class, then not a valid album
                pass

        return albums
    
  
