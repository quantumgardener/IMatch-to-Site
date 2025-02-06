# pip3 install Mastodon.py
import datetime
import html
import logging
import os
import pprint
import random
import re
import subprocess
import sys

from PIL import Image

from imatch_image import IMatchImage
from platform_base import PlatformController
import IMatchAPI as im
import config

MASTER_WIDTH = 800
MASTER_FORMAT = "JPEG"
MASTER_QUALITY = 85
THUMBNAIL_WIDTH = 150
THUMBNAIL_FORMAT = "WEBP"

class QuantumImage(IMatchImage):

    def __init__(self, id, platform) -> None:
        super().__init__(id, platform)
        self.alt_text = None

    def prepare_for_upload(self) -> None:
        """Build variables ready for uploading."""
        super().prepare_for_upload()

        # Remove spaces from keywords
        # self.keywords = [item.replace(" ","") for item in self.keywords]
        # self.keywords = [item.replace("-","") for item in self.keywords]

        if self.circadatecreated != "":
            circa = "ca. "
        else:
            circa = ""
        tmp_description = [f"{self.title} -- {self.headline} (Taken {circa}{self.date_time.strftime("%#d %B %Y")})"]
        tmp_description.append('')
        if len(self.keywords) > 0:
            tmp_description.append(" ".join(["#" + keyword for keyword in self.keywords]))  # Ensure keywords are hashtags
            tmp_description.append('')

        self.full_description = "\n".join(tmp_description)

        return None

    @property
    def is_valid(self) -> bool:
        result = super().is_valid
        for attribute in ['make', 'model']:
            try:
                if getattr(self, attribute).strip() == '':
                    self.errors.append(f"missing {attribute}")
            except AttributeError:
                self.errors.append(f"missing {attribute}")
        return len(self.errors) == 0 and result

    @property
    def is_on_platform(self) -> bool:
        res = im.IMatchAPI.get_attributes("quantum", self.id)
        return len(res) != 0

class QuantumController(PlatformController):

    __MAX_SIZE = 25 * config.MB_SIZE
    __PHOTOS_PATH = "photos"
    __ALBUMS_PATH = "albums"
    __PHOTO_TEMPLATE = "photo"
    __MAP_TEMPLATE = "map"
    __ALBUM_TEMPLATE = "album"
    __CARD_TEMPLATE = "card"
    
    def __init__(self, platform) -> None:
        super().__init__(platform)
        self.preferred_format = im.IMatchAPI.FORMAT_WEBP
        self.allowed_formats = [im.IMatchAPI.FORMAT_WEBP, im.IMatchAPI.FORMAT_JPEG]
        self.templates= {
            QuantumController.__PHOTO_TEMPLATE : None,
            QuantumController.__MAP_TEMPLATE : None,
            QuantumController.__ALBUM_TEMPLATE : None,
            QuantumController.__CARD_TEMPLATE : None,
        }
        
        self.albums = {}

    def classify_images(self):
        super().classify_images()
        for image in self.images:
            for category in image.categories:
                splits = category['path'].split("|")
                match splits[0]:
                    case "Socials":
                        if splits[1] == "flickr":
                            # Need to grab any albums and groups
                            try:
                                if splits[2] == "albums":
                                    # Code is in the description
                                    if splits[3] not in self.albums:
                                        self.albums[splits[3]] = {}
                                        self.albums[splits[3]]['name'] = splits[3]
                                        self.albums[splits[3]]['images'] = set()
                                        self.albums[splits[3]]['id'] = (category['description'].split("\n"))[0].strip()
                                        try:
                                            self.albums[splits[3]]['description'] = (category['description'].split("\n"))[1].strip()
                                        except IndexError:
                                            logging.error(f"{self.name}: Text description missing for {category}")
                                            sys.exit(1)
                                    self.albums[splits[3]]['images'].add(image)
                            except IndexError:
                                pass #no groups or albums found

    def prepare_file_information(self, image):
        """Gather information in a consitent format for writing files and add to image"""
        match = re.search(r'\[(\d+)\]', image.filename)
        if not match:
            raise ValueError(f'{self.name}: Unable to extract digits from filename')
        image.media_id = match.group(1)
        image.target_master = f'{image.media_id}_{MASTER_WIDTH}.{MASTER_FORMAT.lower()}' 
        image.target_thumbnail = f'{image.media_id}_{THUMBNAIL_WIDTH}.{THUMBNAIL_FORMAT.lower()}'
        image.target_md = os.path.join(self.api[QuantumController.__PHOTOS_PATH], f'{image.media_id}.md')

    def write_photo_markdown(self, image):

        map_values = {
            'latitude' : image.latitude,
            'longitude' : image.longitude,
            'key' : im.IMatchAPI.get_application_variable("quantum_map_key")            
        }

        if not image.is_image_in_category(im.IMatchAPI.get_application_variable("quantum_hide_me")):
            map = self.templates[QuantumController.__MAP_TEMPLATE].format(**map_values)
            logging.debug("Map included")
        else:
            map = ""
            logging.debug("Map skipped")
        

        template_values = {
            'aperture' : '{0:.3g}'.format(float(image.aperture)) if image.aperture != "" else "__unknown__",
            'camera' : image.model,
            'date_taken' : image.date_time.strftime('%Y-%m-%dT%H:%M:%S'),
            'description' : html.unescape(f'{image.headline} {image.description.replace("\n", " ")}'),
            'focal_length' : image.focal_length if image.focal_length != "" else "__unknown__",
            'image_path' : image.target_master,
            'iso' : image.iso if image.iso != "" else "__unknown__",
            'lens' : image.lens if image.lens != "" else "__unknown__",
            'location' : image.location,
            'shutter_speed' : image.shutter_speed if image.shutter_speed != "" else "__unknown__",
            'title' : image.title,
            'thumbnail' : image.target_thumbnail,
            'map' : map,
        }

        if( image.latitude == "" or image.longitude == ""):
            raise ValueError(f"Missing latitude and longitude in image {image.name}")

        # OK to overwrite this every time
        md_content = self.templates[QuantumController.__PHOTO_TEMPLATE].format(**template_values)
        ##md_content = html.unescape(md_content)
        ## Clean out lines with "unknown"
        lines = md_content.split("\n")
        filtered_lines = [line for line in lines if "__unknown__" not in line]
        filtered_markdown = "\n".join(filtered_lines)

        with open(image.target_md, 'w') as file:
            file.write(filtered_markdown)

    def create_master(self, image):
        # Resize image
        with Image.open(image.filename) as img:
            width, height = img.size
            aspect_ratio = height / width
            new_height = int(MASTER_WIDTH * aspect_ratio)
            img = img.resize((MASTER_WIDTH, new_height), Image.LANCZOS)
            img.save(self.build_photo_path(image.target_master), format=MASTER_FORMAT, quality=MASTER_QUALITY)

        # Now add back XMP information
        exiftool = r"C:\Program Files\photools.com\imatch6\exiftool.exe"
        exiftool = os.path.normpath(exiftool)
        command = [
            exiftool,
            '-TagsFromFile',
            image.filename,
            '-xmp:CreateDate',
            '-xmp-photoshop:DateCreated',
            '-xmp-dc:Title',
            '-xmp-dc:Description',
            '-xmp-xmpRights:All',
            '-xmp-xmp:Rights',
            '-xmp-dc:rights',
            '-XMP-photoshop:Country',
            '-XMP-photoshop:State',
            '-XMP-photoshop:City',
            '-overwrite_original',
            self.build_photo_path(image.target_master)
        ]

        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logging.error(f"Error copying metadata: {result.stderr}")
                sys.exit(1)
            else:
                logging.debug("Metadata copied successfully.")
        except FileNotFoundError:
            logging.error(f"ExifTool not found at {exiftool}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            sys.exit(1)

        if os.path.getsize(self.build_photo_path(image.target_master)) > QuantumController.__MAX_SIZE:
            self.errors.append(f"file too large")
            raise ValueError("Image too large after conversion")

    def create_thumbnail(self, image):
        with Image.open(image.filename) as img:
            width, height = img.size
            aspect_ratio = height / width
            new_height = int(THUMBNAIL_WIDTH * aspect_ratio)
            img = img.resize((THUMBNAIL_WIDTH, new_height), Image.LANCZOS)
            img.save(self.build_photo_path(image.target_thumbnail), format=THUMBNAIL_FORMAT)

    def connect(self):
        try:
            if self.api is not None:
                return
            else:
                quantum_path = im.IMatchAPI.get_application_variable("quantum_path")
                self.api = {
                    QuantumController.__PHOTOS_PATH : os.path.join(quantum_path, QuantumController.__PHOTOS_PATH),
                    QuantumController.__ALBUMS_PATH : os.path.join(quantum_path, QuantumController.__ALBUMS_PATH)
                }

                if os.path.exists(self.api[QuantumController.__PHOTOS_PATH]) and os.path.isdir(self.api[QuantumController.__PHOTOS_PATH]):
                    photo_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo.md')
                    if os.path.exists(photo_template_filename):
                        with open(photo_template_filename, 'r') as file:
                            self.templates[QuantumController.__PHOTO_TEMPLATE] = file.read()
                    else:
                        logging.error('Connection error: {photo_template_filename} not found.')
                        sys.exit(1)

                    map_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo-map.md')
                    if os.path.exists(map_template_filename):
                        with open(map_template_filename, 'r') as file:
                            self.templates[QuantumController.__MAP_TEMPLATE] = file.read()
                    else:
                        logging.error('Connection error: {map_template_filename} not found.')
                        sys.exit(1)


                else:
                    logging.error(f'Connection error: {self.api[QuantumController.__PHOTOS_PATH]} not found.')
                    sys.exit(1)

                if os.path.exists(self.api[QuantumController.__ALBUMS_PATH]) and os.path.isdir(self.api[QuantumController.__ALBUMS_PATH]):

                    album_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-album.md')
                    if os.path.exists(album_template_filename):
                        with open(album_template_filename, 'r') as file:
                            self.templates[QuantumController.__ALBUM_TEMPLATE] = file.read()
                    else:
                        logging.error(f'Connection error: {album_template_filename} not found.')
                        sys.exit(1)
                    
                    album_card_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-album-card.md')
                    if os.path.exists(album_card_template_filename):
                        with open(album_card_template_filename, 'r') as file:
                            self.templates[QuantumController.__CARD_TEMPLATE] = file.read()
                    else:
                        logging.error(f'Connection error: {album_card_template_filename} not found.')
                        sys.exit(1)

                else:
                    logging.error(f'Connection error: {self.api[QuantumController.__ALBUMS_PATH]} not found.')
                    sys.exit(1)

                print(f'{self.name}: Connected to {quantum_path}.')
        except Exception as e:
            print(f"An unknown exception occurred in connnecting: {e}")
            sys.exit(1)


    def finalise(self):
        self.generate_albums()
        super().finalise()       

    def build_album_path(self, path):
        return os.path.join(self.api[QuantumController.__ALBUMS_PATH], path)
    
    def build_photo_path(self, path):
        return os.path.join(self.api[QuantumController.__PHOTOS_PATH], path)
    
    def commit_add(self, image):
        """Make the api call to commit the image to the platform, and update IMatch with reference details"""
        try:
            self.prepare_file_information(image)
            
            if not os.path.exists(self.build_photo_path(image.target_master)):
                # Add only if not there. We use update flags to replace an existing file
                self.create_master(image)

            if not os.path.exists(self.build_photo_path(image.target_thumbnail)):
                self.create_thumbnail(image)

            self.write_photo_markdown(image)
            
            # Update the image in IMatch by adding the attributes below.
            im.IMatchAPI().set_attributes(self.name, image.id, data = {
                'posted' : datetime.datetime.now().isoformat()[:10],
                'media_id' : image.media_id,
                'url' : f'https://quantumgardener.info/photos/{image.media_id}'
                })
        except KeyError:
            logging.error(f"{self.name}: Missed validating an image field somewhere.")
            sys.exit()
        except ValueError:
            pass
        except Exception as e:
            logging.error(f"{self.name}: An unexpected error occurred: {e}")
            sys.exit()

    def commit_delete(self, image):
        """Make the api call to delete the image from the platform. We assume the file is not linked anywhere else."""
        try:
            self.prepare_file_information(image)

            if os.path.exists(self.build_photo_path(image.target_master)):
                os.remove(self.build_photo_path(image.target_master))
            if os.path.exists(self.build_photo_path(image.target_thumbnail)):
                os.remove(self.build_photo_path(image.target_thumbnail))
            if os.path.exists(self.build_photo_path(image.target_md)):
                os.remove(self.build_photo_path(image.target_md))

        except Exception as e:
            logging.error(f"{self.name}: An unexpected error occurred: {e}")
            sys.exit()

    def commit_update(self, image):
        """Make the api call to update the image on the platform"""
        try:
            self.prepare_file_information(image)

            if image.operation == IMatchImage.OP_UPDATE:
                if os.path.exists(self.build_photo_path(image.target_master)):
                    os.remove(self.build_photo_path(image.target_master))
                self.create_master(image)

                if os.path.exists(self.build_photo_path(image.target_thumbnail)):
                    os.remove(self.build_photo_path(image.target_thumbnail))
                self.create_thumbnail(image)


            self.write_photo_markdown(image)

            # Update the image in IMatch by adding the attributes below.
            im.IMatchAPI().set_attributes(self.name, image.id, data = {
                'posted' : datetime.datetime.now().isoformat()[:10],
                'media_id' : image.media_id,
                'url' : f'https://quantumgardener.info/photos/{image.media_id}'
                })
        except KeyError:
            logging.error(f"{self.name}: validating an image field somewhere.")
            sys.exit()
        except ValueError:
            pass
        except Exception as e:
            logging.error(f"{self.name}: unexpected error occurred: {e}")
            sys.exit()
    
    def generate_albums(self):
        self.connect()

        for album in self.albums.values():
            print(f"{self.name}: Creating album for {album['name']} [{len(album['images'])} images].")
            cards = []
            dates = []
            for image in album['images']:
                self.prepare_file_information(image)
                dates.append(image.date_time)
                card_template_values = {
                    'page' : image.media_id,
                    'title' : image.title,
                    'thumbnail' : image.target_thumbnail,
                }
                card_content = self.templates[QuantumController.__CARD_TEMPLATE].format(**card_template_values)
                cards.append(card_content)
        
            album_template_values = {
                'datetime' : max(dates).strftime('%Y-%m-%dT%H:%M:%S'),
                'title' : album['name'],
                'cards' : "\n".join(cards),
                'description' : album['description'],
                'thumbnail' : random.choice(list(album['images'])).target_thumbnail
            }

            md_content = self.templates[QuantumController.__ALBUM_TEMPLATE].format(**album_template_values)
            md_content = html.unescape(md_content)

            album_filename = self.build_album_path(f"{album['id']}.md")
            logging.debug(f"{self.name}: Writing album to {album_filename}")
            with open(album_filename, 'w') as file:
                file.write(md_content)
