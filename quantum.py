import datetime
import html
import logging
import os
from pprint import pprint
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

SCALING_FACTORS = [
    { "size" : 100, "suffix" : "_t", "format" : "WEBP" },
    { "size" : 240, "suffix" : "_m", "format" : "WEBP" },
    { "size" : 320, "suffix" : "_n", "format" : "WEBP" },
    { "size" : 500, "suffix" : "", "format" : "WEBP" },
    { "size" : 640, "suffix" : "_z", "format" : "WEBP" },
    { "size" : 800, "suffix" : "_c", "format" : "JPEG" },
]

class QuantumImage(IMatchImage):

    def __init__(self, id, platform) -> None:
        super().__init__(id, platform)

    def _prepare_for_operations(self) -> None:
        """Build variables ready for uploading."""
        super()._prepare_for_operations()

        # Format keywords consistently
        self.hierarchical_keywords = [item.replace("|","/") for item in self.hierarchical_keywords]
        self.hierarchical_keywords = [item.replace("--", "-") for item in self.hierarchical_keywords]
        self.hierarchical_keywords = [item.replace(" ","-") for item in self.hierarchical_keywords]

        if self.circadatecreated != "":
            circa = "ca. "
        else:
            circa = ""
        tmp_description = [f"{self.title} -- {self.headline} (Taken {circa}{self.date_time.strftime("%#d %B %Y")})"]
        tmp_description.append('')
        if len(self.flat_keywords) > 0:
            tmp_description.append(" ".join(["#" + keyword for keyword in self.flat_keywords]))  # Ensure keywords are hashtags
            tmp_description.append('')

        self.full_description = "\n".join(tmp_description)

        if not hasattr(self, "description"):
            self.description = ""
        
        match = re.search(r'\[(\d+)\]', self.filename)
        if not match:
            raise ValueError(f'{self.name}: Unable to extract digits from filename')
        self.media_id = match.group(1)
        self.target_md = f'{self.media_id}.md'
        logging.debug(f'media_id: {self.media_id}')
        logging.debug(f'target_md: {self.target_md}')
        
    @property
    def is_valid(self) -> bool:
        result = super().is_valid
        for attribute in ['make', 'model', 'country', 'state']:
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
    
    @property
    def master(self) -> str:
        return f'{self.media_id}_c.{QuantumController._MASTER_FORMAT.lower()}'

    @property
    def thumbnail(self) -> str:
        return f'{self.media_id}_t.{QuantumController._THUMBNAIL_FORMAT.lower()}'

class QuantumController(PlatformController):

    _MAX_SIZE = 25 * config.MB_SIZE
    _PHOTOS_PATH = "photos"
    _ALBUMS_PATH = "albums"
    _PHOTO_TEMPLATE = "photo"
    _MAP_TEMPLATE = "map"
    _ALBUM_TEMPLATE = "album"
    _CARD_TEMPLATE = "card"
    _MASTER_FORMAT = "JPEG"
    _THUMBNAIL_FORMAT = "WEBP"
    
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
            if image.operation != IMatchImage.OP_INVALID:
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
                                        try:
                                            self.albums[name].add(image)
                                        except KeyError:
                                            logging.error(f'{self.name}: Unknown album "{name}". Check data.json.')
                                            sys.exit(1)
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
            for keyword in sorted(image.hierarchical_keywords):
                property_keywords.add(f"keyword/{keyword}")

            for location in image.location.split(", "):
                property_keywords.add(f"keyword/{location.lower()}")

            # for album in self.albums.values():
            #     if image in album.images:
            #         property_keywords.add(f"album/{album.id}")

            template_values = {
                'ai_description' : html.unescape(image.ai_description),
                'aperture' : '{0:.3g}'.format(float(image.aperture)) if image.aperture != "" else "_unknown_",
                'camera' : image.model,
                'date_taken' : image.date_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'description' : html.unescape(f'{image.headline} {image.description.replace("\n", " ")}') if image.description != "" else "_unknown_",
                'focal_length' : image.focal_length if image.focal_length != "" else "_unknown_",
                'image_path' : image.master,
                'iso' : image.iso if image.iso != "" else "_unknown_",
                'lens' : image.lens if image.lens != "" else "_unknown_",
                'location' : image.location,
                'property_keywords' : "\n".join(f"  - {item}" for item in sorted(property_keywords)),
                'shutter_speed' : image.shutter_speed if image.shutter_speed != "" else "_unknown_",
                'title' : image.title,
                'thumbnail' : f"[[{image.thumbnail}]]",
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

    def create_image(self, image, output_file, long_edge, format, quality=85):
        """Create image from original as specified"""

        logging.debug(f"Creating image: {output_file}")
        with Image.open(image.filename) as img:
            width, height = img.size
            scaling_factor = int(long_edge) / max(width, height)
            new_size = (int(width * scaling_factor), int(height * scaling_factor))
            img = img.resize(new_size, Image.LANCZOS)
            img.save(output_file, format=format, quality=quality)

        if format == "JPEG":
            # Add back XMP information
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
                output_file
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

        if os.path.getsize(output_file) > QuantumController._MAX_SIZE:
            self.errors.append(f"file too large")
            raise ValueError("Image too large after conversion")

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
           
            # Because we're adding, assume all existing images are to be overwritten
            for scale in SCALING_FACTORS:
                output_file = self.build_photo_path(f'{image.media_id}{scale['suffix']}.{scale['format'].lower()}')
                self.create_image(image, output_file, scale['size'], scale['format'])

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

            # Delete all existing files
            for scale in SCALING_FACTORS:
                output_file = self.build_photo_path(f'{image.media_id}{scale['suffix']}.{scale['format'].lower()}')
                if os.path.exists(output_file):
                    os.remove(output_file)

            if os.path.exists(self.build_photo_path(image.target_md)):
                os.remove(self.build_photo_path(image.target_md))

        except Exception as e:
            logging.error(f"{self.name}: An unexpected error occurred: {e}")
            sys.exit()

    def commit_update(self, image):
        """Make the api call to update the image on the platform"""
        try:

            # To reduce sync load into Obsidian, only create image files
            # if they are missing or older than original.
            for scale in SCALING_FACTORS:
                output_file = self.build_photo_path(f'{image.media_id}{scale['suffix']}.{scale['format'].lower()}')
                if os.path.exists(output_file) and image.operation == IMatchImage.OP_METADATA:
                    # Check file modified dates. Metadata writes will update and that's desired.
                    original_date = os.path.getmtime(image.filename)
                    output_date = os.path.getmtime(output_file)
                    if original_date > output_date:
                        print(f"{self.name}: Image file metadata changed. Regenerating {output_file}")
                        self.create_image(image, output_file, scale['size'], scale['format'])
                else:
                    # File for this scale does not exist or forced update
                    self.create_image(image, output_file, scale['size'], scale['format'])

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
            if(len(album) > 0):
                print(f"{self.name}: Creating album for {album.name} [{len(album)} images].")
                cards = []
                dates = []
                for image in album.images:
                    dates.append(image.date_time)
                    card_template_values = {
                        'page' : image.media_id,
                        'title' : image.title,
                        'thumbnail' : image.thumbnail,
                    }
                    card_content = self.templates[QuantumController._CARD_TEMPLATE].format(**card_template_values)
                    cards.append(card_content)

                album_template_values = {
                    'datetime' : max(dates).strftime('%Y-%m-%dT%H:%M:%S'),
                    'title' : album.name,
                    'cards' : "\n".join(cards),
                    'description' : album.description,
                    'thumbnail' : random.choice(list(album.images)).thumbnail
                }

                md_content = self.templates[QuantumController._ALBUM_TEMPLATE].format(**album_template_values)
                md_content = html.unescape(md_content)

                album_filename = self.build_album_path(f"{album.id}.md")
                logging.debug(f"{self.name}: Writing album to {album_filename}")
                with open(album_filename, 'w') as file:
                    file.write(md_content)
            else:
                print(f"{self.name}: Skipping empty album {album.name}.")