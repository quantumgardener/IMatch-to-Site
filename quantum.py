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
from platform_controller import PlatformController
from album import Album
import IMatchAPI as im
import config

class QuantumImage(IMatchImage):

    _MASTER_WIDTH = 800
    _MASTER_FORMAT = "JPEG"
    _MASTER_QUALITY = 85
    _THUMBNAIL_WIDTH = 150
    _THUMBNAIL_FORMAT = "WEBP"

    def _init_(self, id, platform) -> None:
        super()._init_(id, platform)
        self.alt_text = None

    def _prepare_for_operations(self) -> None:
        """Build variables ready for uploading."""
        super()._prepare_for_operations()

        # Format keywords consistently
        self.keywords = [item.replace(" ","-") for item in self.keywords]
        self.keywords = [item.lower() for item in self.keywords]

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

        match = re.search(r'\[(\d+)\]', self.filename)
        if not match:
            raise ValueError(f'{self.name}: Unable to extract digits from filename')
        self.media_id = match.group(1)
        self.target_md = f'{self.media_id}.md'
        self.target_master = f'{self.media_id}_{QuantumImage._MASTER_WIDTH}.{QuantumImage._MASTER_FORMAT.lower()}' 
        self.target_thumbnail = f'{self.media_id}_{QuantumImage._THUMBNAIL_WIDTH}.{QuantumImage._THUMBNAIL_FORMAT.lower()}'

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

    _MAX_SIZE = 25 * config.MB_SIZE
    _PHOTOS_PATH = "photos"
    _ALBUMS_PATH = "albums"
    _PHOTO_TEMPLATE = "photo"
    _MAP_TEMPLATE = "map"
    _ALBUM_TEMPLATE = "album"
    _CARD_TEMPLATE = "card"
    
    def __init__(self, platform_name, preferred_format, allowed_formats):
        super().__init__(platform_name, preferred_format, allowed_formats)

        self.templates = {
            QuantumController._PHOTO_TEMPLATE : None,
            QuantumController._MAP_TEMPLATE : None,
            QuantumController._ALBUM_TEMPLATE : None,
            QuantumController._CARD_TEMPLATE : None,
        }    
        logging.debug(f'{self.name}: Instance initialised.')

    def classify_images(self):
        super().classify_images()
        for image in self.images:
            for category in image.categories:
                splits = category['path'].split("|")
                match splits[0]:
                    case "Socials":
                        if splits[1] == self.name:
                            # Need to grab any albums and groups
                            try:
                                if splits[2] == "albums":
                                    # Code is in the description
                                    name = splits[3]
                                    album = self.get_album(name)
                                    if album is None:
                                        id = (category['description'].split("\n"))[0].strip()
                                        try:
                                            description = (category['description'].split("\n"))[1].strip()
                                        except IndexError:
                                            logging.error(f"{self.name}: Text description missing for {category}")
                                            sys.exit(1)
                                        album = Album(name, id, description)
                                        self.add_album(album)
                                    album.add(image)
                            except IndexError:
                                pass #no groups or albums found

    def write_photo_markdown(self, image):

        try:

            map_values = {
                'latitude' : image.latitude,
                'longitude' : image.longitude,
                'key' : im.IMatchAPI.get_application_variable("quantum_map_key")            
            }

            if not image.is_image_in_category(im.IMatchAPI.get_application_variable("quantum_hide_me")):
                map = self.templates[QuantumController._MAP_TEMPLATE].format(**map_values)
                logging.debug("Map included")
            else:
                map = ""
                logging.debug("Map skipped")

            property_keywords = {"class/photo"}
            for keyword in image.keywords:
                property_keywords.add(f"keyword/{keyword}")      

            template_values = {
                'aperture' : '{0:.3g}'.format(float(image.aperture)) if image.aperture != "" else "_unknown_",
                'camera' : image.model,
                'date_taken' : image.date_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'description' : html.unescape(f'{image.headline} {image.description.replace("\n", " ")}'),
                'focal_length' : image.focal_length if image.focal_length != "" else "_unknown_",
                'image_path' : image.target_master,
                'iso' : image.iso if image.iso != "" else "_unknown_",
                'lens' : image.lens if image.lens != "" else "_unknown_",
                'location' : image.location,
                'property_keywords' : "\n".join(f"  - {item}" for item in sorted(property_keywords)),
                'shutter_speed' : image.shutter_speed if image.shutter_speed != "" else "_unknown_",
                'title' : image.title,
                'thumbnail' : image.target_thumbnail,
                'map' : map,
            }

            if( image.latitude == "" or image.longitude == ""):
                raise ValueError(f"Missing latitude and longitude in image {image.name}")

            # OK to overwrite this every time
            md_content = self.templates[QuantumController._PHOTO_TEMPLATE].format(**template_values)

            ## Clean out lines with "unknown"
            lines = md_content.split("\n")
            filtered_lines = [line for line in lines if "_unknown_" not in line]
            filtered_markdown = "\n".join(filtered_lines)

        except KeyError as e:
            print(f"No value for {e} in template")
            sys.exit(1)
 
        with open(os.path.join(self.api[QuantumController._PHOTOS_PATH], image.target_md), 'w') as file:
            file.write(filtered_markdown)

    def create_master(self, image):
        # Resize image
        with Image.open(image.filename) as img:
            width, height = img.size
            aspect_ratio = height / width
            new_height = int(QuantumImage._MASTER_WIDTH * aspect_ratio)
            img = img.resize((QuantumImage._MASTER_WIDTH, new_height), Image.LANCZOS)
            img.save(self.build_photo_path(image.target_master), format=QuantumImage._MASTER_FORMAT, quality=QuantumImage._MASTER_QUALITY)

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

        if os.path.getsize(self.build_photo_path(image.target_master)) > QuantumController._MAX_SIZE:
            self.errors.append(f"file too large")
            raise ValueError("Image too large after conversion")

    def create_thumbnail(self, image):
        with Image.open(image.filename) as img:
            width, height = img.size
            aspect_ratio = height / width
            new_height = int(QuantumImage._THUMBNAIL_WIDTH * aspect_ratio)
            img = img.resize((QuantumImage._THUMBNAIL_WIDTH, new_height), Image.LANCZOS)
            img.save(self.build_photo_path(image.target_thumbnail), format=QuantumImage._THUMBNAIL_FORMAT)

    def connect(self):
        try:
            if self.api is not None:
                return
            else:
                quantum_path = im.IMatchAPI.get_application_variable("quantum_path")
                self.api = {
                    QuantumController._PHOTOS_PATH : os.path.join(quantum_path, QuantumController._PHOTOS_PATH),
                    QuantumController._ALBUMS_PATH : os.path.join(quantum_path, QuantumController._ALBUMS_PATH)
                }

                logging.debug(f"checking for {self.api[QuantumController._PHOTOS_PATH]}.")
                if os.path.exists(self.api[QuantumController._PHOTOS_PATH]) and os.path.isdir(self.api[QuantumController._PHOTOS_PATH]):
                    photo_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo.md')
                    if os.path.exists(photo_template_filename):
                        with open(photo_template_filename, 'r') as file:
                            self.templates[QuantumController._PHOTO_TEMPLATE] = file.read()
                    else:
                        logging.error('Connection error: {photo_template_filename} not found.')
                        sys.exit(1)

                    map_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo-map.md')
                    if os.path.exists(map_template_filename):
                        with open(map_template_filename, 'r') as file:
                            self.templates[QuantumController._MAP_TEMPLATE] = file.read()
                    else:
                        logging.error('Connection error: {map_template_filename} not found.')
                        sys.exit(1)


                else:
                    logging.error(f'Connection error: {self.api[QuantumController._PHOTOS_PATH]} not found.')
                    sys.exit(1)

                if os.path.exists(self.api[QuantumController._ALBUMS_PATH]) and os.path.isdir(self.api[QuantumController._ALBUMS_PATH]):

                    album_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-album.md')
                    if os.path.exists(album_template_filename):
                        with open(album_template_filename, 'r') as file:
                            self.templates[QuantumController._ALBUM_TEMPLATE] = file.read()
                    else:
                        logging.error(f'Connection error: {album_template_filename} not found.')
                        sys.exit(1)
                    
                    album_card_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-album-card.md')
                    if os.path.exists(album_card_template_filename):
                        with open(album_card_template_filename, 'r') as file:
                            self.templates[QuantumController._CARD_TEMPLATE] = file.read()
                    else:
                        logging.error(f'Connection error: {album_card_template_filename} not found.')
                        sys.exit(1)

                else:
                    logging.error(f'Connection error: {self.api[QuantumController._ALBUMS_PATH]} not found.')
                    sys.exit(1)

                print(f'{self.name}: Connected to {quantum_path}.')
        except Exception as e:
            print(f"An unknown exception occurred in connnecting: {e}")
            sys.exit(1)


    def finalise(self):
        self.generate_albums()
        super().finalise()       

    def build_album_path(self, path):
        return os.path.join(self.api[QuantumController._ALBUMS_PATH], path)
    
    def build_photo_path(self, path):
        return os.path.join(self.api[QuantumController._PHOTOS_PATH], path)
    
    def commit_add(self, image):
        """Make the api call to commit the image to the platform, and update IMatch with reference details"""
        try:
           
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

        for album in sorted(self.albums.values()):
            print(f"{self.name}: Creating album for {album.name} [{len(album.images)} images].")
            cards = []
            dates = []
            for image in album.images:
                dates.append(image.date_time)
                card_template_values = {
                    'page' : image.media_id,
                    'title' : image.title,
                    'thumbnail' : image.target_thumbnail,
                }
                card_content = self.templates[QuantumController._CARD_TEMPLATE].format(**card_template_values)
                cards.append(card_content)
        
            album_template_values = {
                'datetime' : max(dates).strftime('%Y-%m-%dT%H:%M:%S'),
                'title' : album.name,
                'cards' : "\n".join(cards),
                'description' : album.description,
                'thumbnail' : random.choice(list(album.images)).target_thumbnail
            }

            md_content = self.templates[QuantumController._ALBUM_TEMPLATE].format(**album_template_values)
            md_content = html.unescape(md_content)

            album_filename = self.build_album_path(f"{album.id}.md")
            logging.debug(f"{self.name}: Writing album to {album_filename}")
            with open(album_filename, 'w') as file:
                file.write(md_content)
