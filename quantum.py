from concurrent.futures import ProcessPoolExecutor
import datetime
import html
import logging
import os
from pprint import pprint
import random
import subprocess
import sys

from PIL import Image

from imatch_image import IMatchImage
from platform_controller import PlatformController
from album import Album
import IMatchAPI as im
import config
import scan_files

SCALING_FACTORS = [
    { "size" : 100, "suffix" : "_t", "format" : "WEBP" },
    { "size" : 240, "suffix" : "_m", "format" : "WEBP" },
    { "size" : 320, "suffix" : "_n", "format" : "WEBP" },
    { "size" : 500, "suffix" : "", "format" : "WEBP" },
    { "size" : 640, "suffix" : "_z", "format" : "WEBP" },
    { "size" : 800, "suffix" : "_c", "format" : "WEBP" },
    { "size" : 1024, "suffix" : "_b", "format" : "WEBP" },
    { "size" : 1600, "suffix" : "_h", "format" : "WEBP" },
]

exiftool_public_tag_args = [
    "-xmp:CreateDate",
    "-xmp-photoshop:DateCreated",
    "-xmp-dc:Title",
    "-xmp-dc:Description",
    "-xmp-xmpRights:All",
    "-xmp-xmp:Rights",
    "-xmp-dc:rights",
    "-XMP-photoshop:Country",
    "-XMP-photoshop:State",
    "-XMP-photoshop:City",
    "-XMP-iptcCore:Location",
    "-overwrite_original"
]

exiftool_private_tag_args = [
    "-xmp:CreateDate",
    "-xmp-photoshop:DateCreated",
    "-xmp-dc:Title",
    "-xmp-dc:Description",
    "-xmp-xmpRights:All",
    "-xmp-xmp:Rights",
    "-xmp-dc:rights",
    "-XMP-photoshop:Country",
    "-XMP-photoshop:State",
    "-XMP-photoshop:City",
    "-overwrite_original"
]

def create_image_version(input_file, output_file, long_edge, format, quality=85):
    """Create image from original as specified"""
    logging.debug(f"Creating image: {output_file}")
    with Image.open(input_file) as img:
        width, height = img.size
        if max(width,height) > long_edge:
            scaling_factor = int(long_edge) / max(width, height)
            new_size = (int(width * scaling_factor), int(height * scaling_factor))
            img = img.resize(new_size, Image.LANCZOS)
        img.save(output_file, format=format, quality=quality)


def prepare_image_versions(args):
    return create_image_version(*args)


def set_metadata(exiftool_tasks):
    with ExifToolSession() as et:    
        for src, tgt, isPrivate in exiftool_tasks:
            try:
                args = exiftool_private_tag_args if isPrivate else exiftool_public_tag_args
                cmd = ['-TagsFromFile', src] + args + [tgt]
                response = et.send(cmd)
                logging.debug(f"[{tgt}] Metadata copied successfully.\n{response.strip()}")
            except Exception as e:
                logging.error(f"Failed to copy metadata to {tgt}: {e}")


class ExifToolSession:
    def __enter__(self):
        self.process = subprocess.Popen(
            [os.path.normpath(r"C:\Program Files\photools.com\imatch6\exiftool.exe"), '-stay_open', 'True', '-@', '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        return self

    def send(self, commands):
        block = '\n'.join(commands) + '\n-execute\n'
        self.process.stdin.write(block)
        self.process.stdin.flush()

        output = ''
        while True:
            line = self.process.stdout.readline()
            if line.strip() == '{ready}':
                break
            output += line
        return output

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.process.stdin.write('-stay_open\nFalse\n')
        self.process.stdin.flush()
        self.process.terminate()

class QuantumImage(IMatchImage):
        
    _PHOTO_TEMPLATE = "photo"
    _MAP_TEMPLATE = "map"

    def __init__(self, id, platform) -> None:
        super().__init__(id, platform)
        self.albums = set()
        self.templates = {
            QuantumImage._PHOTO_TEMPLATE : None,
            QuantumImage._MAP_TEMPLATE : None,
        }    

        photo_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo.md')
        if os.path.exists(photo_template_filename):
            with open(photo_template_filename, 'r') as file:
                self.templates[QuantumImage._PHOTO_TEMPLATE] = file.read()
        else:
            logging.error('Connection error: {photo_template_filename} not found.')
            sys.exit(1)

        map_template_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)),'quantum-photo-map.md')
        if os.path.exists(map_template_filename):
            with open(map_template_filename, 'r') as file:
                self.templates[QuantumImage._MAP_TEMPLATE] = file.read()
        else:
            logging.error('Connection error: {map_template_filename} not found.')
            sys.exit(1)

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
        
        self.target_md = f'{self.media_id}.md'
        logging.debug(f'media_id: {self.media_id}')
        logging.debug(f'target_md: {self.target_md}')
        
    @property
    def is_valid(self) -> bool:
        result = super().is_valid
        for attribute in ['make', 'model', 'country', 'state', 'copyright', 'copyrightmarked', 'copyrighturl']:
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
        return self.filename_for_size("c")

    @property
    def thumbnail(self) -> str:
        return self.filename_for_size("m")
    
    def filename_for_size(self, size: str) -> str:
        return f'{self.media_id}_{size.lower()}.webp'
    
    
    def create_photo_markdown(self):
        try:
            display_location = []
            if len(self.location) > 0: 
                try:
                    if self.isPublic:
                        for part in reversed(self.location.split(", ")):
                            display_location.append(html.unescape(part))
                except KeyError:
                    for part in reversed(self.location.split(", ")):
                        display_location.append(html.unescape(part))
            if len(self.city) > 0:
                display_location.append(html.unescape(self.city))
            if len(self.state) > 0:
                display_location.append(html.unescape(self.state))
            if len(self.country) > 0:
                display_location.append(html.unescape(self.country))

            map = ""
            map_values = {
                'latitude' : self.latitude,
                'longitude' : self.longitude,
                'key' : im.IMatchAPI.get_application_variable("quantum_map_key")            
            }
            try:
                if self.isPublic:
                    map = self.templates[QuantumImage._MAP_TEMPLATE].format(**map_values)
            except KeyError:
                map = self.templates[QuantumImage._MAP_TEMPLATE].format(**map_values)
 


            property_keywords = {"class/photo"}
            for keyword in sorted(self.hierarchical_keywords):
                property_keywords.add(f"keyword/{keyword}")
            for location in display_location:
                property_keywords.add(html.unescape(f"keyword/{location.lower().replace(' ','-').replace("'","")}")) ## lowercase and replace spaces

            albums = set()
            for album in self.controller.albums.values():
                if self in album.images:
                    albums.add(album)

            albumlist = "_unknown_"
            if len(albums) > 0:
                sorted_albums = sorted(albums, key=lambda x: x.name)
                if len(sorted_albums) > 1:
                    albumlist = ", ".join(f'[[{a.id}\\|{a.name}]]' for a in sorted_albums[:-1]) + " and " + f'[[{sorted_albums[-1].id}\\|{sorted_albums[-1].name}]]'
                else:
                    albumlist = f'[[{sorted_albums[0].id}\\|{sorted_albums[0].name}]]'

            match self.cameraname:
                case "Canon EOS 400D DIGITAL":
                    camera = "Canon EOS 400D"
                case _ if self.cameraname.startswith("Apple"):
                    camera = f'Apple iPhone\\|{self.cameraname}'
                case _:
                    camera = self.cameraname

            description = ""
            if self.description != "":
                description = html.unescape(f'{self.headline} {self.description.replace("\n", " ")} ')

            albums = "_unknown_"
            if len(albums) > 0:
                albums = f"This photo appears in {albumlist}."

            template_values = {
                'ai_description' : html.unescape(self.ai_description),
                'albums' : albums,
                'aperture' : '{0:.3g}'.format(float(self.aperture)) if self.aperture != "" else "_unknown_",
                'camera' : camera,
                'date_taken' : self.date_time.strftime('%Y-%m-%dT%H:%M:%S'),
                'description' : description,
                'focal_length' : self.focal_length.replace(" mm","mm") if self.focal_length != "" else "_unknown_",
                'image_path' : self.master,
                'iso' : self.iso if self.iso != "" else "_unknown_",
                'lens' : self.lens if self.lens != "" else "_unknown_",
                'location' : ', '.join(display_location),
                'property_keywords' : "\n".join(f"  - {item}" for item in sorted(property_keywords)),
                'orientation' : 'landscape' if self.width >= self.height else 'portrait',
                'shutter_speed' : self.shutter_speed if self.shutter_speed != "" else "_unknown_",
                'title' : self.title,
                'thumbnail' : f"[[{self.thumbnail}]]",
                'map' : map,
            }

            if( self.latitude == "" or self.longitude == ""):
                raise ValueError(f"Missing latitude and longitude in image {self.name}")

            # OK to overwrite this every time
            md_content = self.templates[QuantumImage._PHOTO_TEMPLATE].format(**template_values)

            ## Clean out lines with "unknown"
            lines = md_content.split("\n")
            filtered_lines = [line for line in lines if "_unknown_" not in line]
            filtered_markdown = "\n".join(filtered_lines)

        except KeyError as e:
            print(f"No value for {e} in template")
            sys.exit(1)
 
        output_file = self.controller.build_photo_path(self.target_md)
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(filtered_markdown)


class QuantumController(PlatformController):

    _MAX_SIZE = 25 * config.MB_SIZE
    _PHOTOS_PATH = "photos"
    _ALBUMS_PATH = "albums"
    _ALBUM_TEMPLATE = "album"
    _CARD_TEMPLATE = "card"
    
    def __init__(self, platform_name, preferred_format, allowed_formats):
        super().__init__(platform_name, preferred_format, allowed_formats)     

        self.templates = {
            QuantumController._ALBUM_TEMPLATE : None,
            QuantumController._CARD_TEMPLATE : None,
        }

        logging.debug(f'{self.name}: Instance initialised.')

    def add_images(self):
        super().add_images()

        scaling_tasks = []
        exiftool_tasks = []
        # Bulk process creation of image version files
        for image in self.images_to_add:
            for scale in SCALING_FACTORS:
                output_file = self.build_photo_path(f'{image.media_id}{scale['suffix']}.{scale['format'].lower()}')
                scaling_tasks.append((image.filename, output_file, scale['size'], scale['format']))
                exiftool_tasks.append((image.filename, output_file, image.isPrivate))

        if (len(scaling_tasks) > 0):
            print(f'{self.name}: Generating image versions (adds)')
            with ProcessPoolExecutor() as executor:
                executor.map(prepare_image_versions, scaling_tasks)

            set_metadata(exiftool_tasks)
            
    
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

        if len(self.images_to_delete) > 0:
            pattern = r"\d{6}_[cmntz]\.webp"
            self.image_references = scan_files.scan_folder_with_subfolders(im.IMatchAPI.get_application_variable("quantum_path"), pattern, {"photos", "albums", ".obsidian"})

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
                if not(os.path.exists(self.api[QuantumController._PHOTOS_PATH]) and os.path.isdir(self.api[QuantumController._PHOTOS_PATH])):
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
           
            image.create_photo_markdown()
            
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

            md_path = self.build_photo_path(image.target_md)
            if os.path.exists(md_path):
                os.remove(self.build_photo_path(md_path))

        except Exception as e:
            logging.error(f"{self.name}: An unexpected error occurred: {e}")
            sys.exit()

    def commit_update(self, image):
        """Make the api call to update the image on the platform"""
        try:
            image.create_photo_markdown()

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
    
    def delete_images(self):
        if len(self.images_to_delete) == 0:
            return  # Nothing to see here

        for image in self.images_to_delete.copy():
            if image.media_id in self.image_references.keys():
                self.images_to_delete.remove(image)
                print(f'{self.name}: Image in use "{image.title}" ({image.media_id})')
                image.errors.append("referenced file")
                self.invalid_images.add(image)
                for referenced_image in self.image_references[image.media_id]:
                    print(f"--{referenced_image[0]}")

        super().delete_images()
        
    def update_images(self):
        super().update_images()

        scaling_tasks = []
        exiftool_tasks = []
        # Bulk process creation of image version files
        for image in self.images_to_update:
            # To reduce sync load into Obsidian, only create image files
            # if they are missing or older than original.
            for scale in SCALING_FACTORS:
                output_file = self.build_photo_path(f'{image.media_id}{scale['suffix']}.{scale['format'].lower()}')
                if os.path.exists(output_file) and image.operation == IMatchImage.OP_METADATA:
                    # Check file modified dates. Metadata writes will update and that's desired.
                    original_date = os.path.getmtime(image.filename)
                    output_date = os.path.getmtime(output_file)
                    if original_date > output_date:
                        logging.debug(f"{self.name}: Image file metadata changed. Regenerating {output_file}")
                        scaling_tasks.append((image.filename, output_file, scale['size'], scale['format']))
                        exiftool_tasks.append((image.filename, output_file, image.isPrivate))
                else:
                    # File for this scale does not exist or forced update
                    scaling_tasks.append((image.filename, output_file, scale['size'], scale['format']))
                    exiftool_tasks.append((image.filename, output_file, image.isPrivate))

        if (len(scaling_tasks) > 0):
            print(f'{self.name}: Generating image versions (updates)')
            with ProcessPoolExecutor() as executor:
                executor.map(prepare_image_versions, scaling_tasks)

            set_metadata(exiftool_tasks)
        
            
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
                        'fullsize' : image.filename_for_size('c'),
                        'page' : image.media_id,
                        'orientation' : 'landscape' if image.width >= image.height else 'portrait',
                        'title' : image.title,
                        'thumbnail' : image.filename_for_size('m'),
                    }
                    card_content = self.templates[QuantumController._CARD_TEMPLATE].format(**card_template_values)
                    cards.append(card_content)

                album_template_values = {
                    'datetime' : max(dates).strftime('%Y-%m-%dT%H:%M:%S'),
                    'title' : album.name,
                    'cards' : "\n".join(cards),
                    'count' : len(cards),
                    'description' : album.description,
                    'thumbnail' : random.choice(list(album.images)).filename_for_size('m')
                }

                md_content = self.templates[QuantumController._ALBUM_TEMPLATE].format(**album_template_values)
                md_content = html.unescape(md_content)

                album_filename = self.build_album_path(f"{album.id}.md")
                logging.debug(f"{self.name}: Writing album to {album_filename}")
                with open(album_filename, 'w') as file:
                    file.write(md_content)
            else:
                print(f"{self.name}: Skipping empty album {album.name}.")

