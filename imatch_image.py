from datetime import datetime
import logging
from pprint import pprint
import re
import sys

import IMatchAPI as im
import config

logging.getLogger('urllib3').setLevel(logging.INFO) # Don't want this debug level to cloud ours

class IMatchImage():

    ERROR_INDICATOR = im.IMatchAPI.COLLECTION_PINS_RED
    OP_INVALID = -1
    OP_NONE = 0
    OP_ADD = 1
    OP_UPDATE = 2
    OP_DELETE = 3
    OP_METADATA = 4

    def __init__(self, id, controller) -> None:
        self.id = id
        self.media_id = None
        self.errors = []    # hold any errors raised during the process
        self.controller = controller 
        self.controller.register_image(self)

        self._fetch_information_from_imatch()
        self._set_operations()
        if self.operation != IMatchImage.OP_INVALID:
            self._prepare_for_operations()
            logging.debug(f'{self.name}: Prepared for operations (opcode: {self.operation}).')
        else:
            logging.debug(f'NO_OP: {self.name}')

    def _fetch_information_from_imatch(self):
        # Get this image's information from IMatch. Process and save each
        # as an attribute for easier reference.
        image_params = {
            "fields" : "datetime,filename,format,name,size", 
            "tagtitle" : "title",
            "tagdescription" : "description",
            "taghierarchical_keywords" : "hierarchicalkeywords",
            "varaperture" : "{File.MD.aperture}",
            "varfocal_length" : "{File.MD.focallength|value:formatted}",
            "varheadline" : "{File.MD.headline}",
            "variso" : "{File.MD.iso|value:formatted}", 
            "varlens" : "{File.MD.lens}",
            "varmake" : "{File.MD.make}",
            "varmodel" : "{File.MD.model}",
            "varcameraname" : "{File.MD.photools.com::IMatch\\1510\\cameraname\\0}",
            "varshutter_speed" : "{File.MD.shutterspeed|value:formatted}",
            "varlatitude" : "{File.MD.gpslatitude|value:rawfrm}",
            "varlongitude" : "{File.MD.gpslongitude|value:rawfrm}",
            "varcircadatecreated" : "{File.MD.XMP::iptcExt\\CircaDateCreated\\CircaDateCreated\\0}",
            "varai_description" : "{File.MD.photools.com::IMatch\\200020\\AI.description\\0}",
            "varcountry" : "{File.MD.Composite\\MWG-Country\\Country\\0}",
            "varstate" : "{File.MD.Composite\\MWG-State\\State\\0}",
            "varcity" : "{File.MD.Composite\\MWG-City\\City\\0}",
            "varcopyright" : "{File.MD.XMP::dc\\rights\\Rights\\0}",
            "varcopyrightmarked" : "{File.MD.XMP::xmpRights\\Marked\\Marked\\0}",
            "varcopyrighturl" : "{File.MD.XMP::xmpRights\\WebStatement\\WebStatement\\0}"
        }
        

        logging.debug("Querying image parameters")
        image_info = im.IMatchAPI.get_file_metadata([self.id],image_params)[0]

        for attribute in image_info.keys():
            match attribute:
                case "dateTime":
                    setattr(self, "date_time", datetime.strptime(image_info[attribute],'%Y-%m-%dT%H:%M:%S'))
                    logging.debug(f'Setting date_time to {image_info[attribute]}')
                case "fileName":    # fileName is a special case. Ask for filename, get fileName in results
                    setattr(self, "filename", image_info[attribute])
                    logging.debug(f'Setting filename to {image_info[attribute]}')
                case "name":
                    match = re.search(r'\[(\d+)\]', image_info[attribute])
                    if match:
                        self.media_id = match.group(1)
                        setattr(self, attribute, image_info[attribute])
                    else:
                        print(f"Unable to extract media_id from {image_info[attribute]}")
                        sys.exit()
                case "model":
                    if image_info[attribute] == "Canon EOS 400D DIGITAL":
                        setattr(self, attribute, "Canon EOS 400D")
                        logging.debug(f'Setting model to Canon EOS 400D')
                    else:
                        setattr(self, attribute, image_info[attribute])
                        logging.debug(f'Setting {attribute} to {image_info[attribute]}')
                case other:      
                    setattr(self, attribute, image_info[attribute])
                    logging.debug(f'Setting {attribute} to {image_info[attribute]}')

        # Retrieve the list of categories the image belongs to.
        logging.debug("Querying characteristics")
        self.categories = im.IMatchAPI.get_file_categories([self.id], params={
            'fields' : 'path,description'}
            )[self.id]
        
        # Retrieve relations for this image. If there is an image in the preferred upload format for the
        # image controller, use it
        self.relations = im.IMatchAPI.get_relations(self.id)
        if self.relations is not None:
            for relation in self.relations:
                if relation['format'] in self.controller.allowed_formats:
                    if self.format != self.controller.preferred_format:
                        # We are ok to replace the existing format. If it is already the preferred, we don't replace again
                            logging.debug(f'Replacing {self.name} with {relation['name']}')
                            logging.debug(f'Setting name to {relation['format']}')
                            self.name = relation['name']
                            logging.debug(f'Setting filename to {relation['fileName']}')
                            self.filename = relation['fileName']
                            logging.debug(f'Setting format to {relation['format']}')
                            self.format = relation['format']
                            logging.debug(f'Setting size to {relation['size']}')
                            self.size = relation['size']

    def _prepare_for_operations(self):
        """Build variables ready for operations."""
        self.flat_keywords = set()  # These are the keywords to output. self.hierachy_keywords is what comes in.
        try:
            for keyword in self.hierarchical_keywords:
                for k in keyword.split("|"):
                    self.add_flat_keyword(k) 
        except AttributeError:
            logging.error("hierarchical keywords missing on image but image has been marked valid.")

        locations = []
        for l in ['country', 'state', 'city']:
            if len(getattr(self, l)) > 0: 
                locations.append(getattr(self, l))
        self.location = ", ".join(locations)

        # Add certain categories as keywords
        logging.debug("Processing base categories")
        for categories in self.categories:
            splits = categories['path'].split("|")
            logging.debug(splits)
            match splits[0]:
                case 'Image Characteristics':
                    match splits[1]:
                        case "Genre":
                            # Genre is tagged with itself and with "photography appended"
                            for genre in splits[2:]:
                                self.flat_keywords.add(genre)
                                logging.debug(f'Added {genre} genre to keywords')

    def _set_operations(self):
        # Set the operation for this file.
        self.operation = IMatchImage.OP_NONE
        if self.is_valid:
            if not self.is_on_platform:
                self.operation = IMatchImage.OP_ADD
            else:
                # Check collections for overriding instructions
                if (self.wants_update or self.wants_metadata) and self.wants_delete:
                    # We have conflicting instructions. 
                    self.errors.append(f"Conflicting instructions. Images is in both {IMatchImage.config.DELETE_CATEGORY} and {IMatchImage.config.UPDATE_CATEGORY} or {IMatchImage.config.UPDATE_METADATA_CATEGORY} categories.")
                    self.operation = IMatchImage.OP_INVALID
                else:
                    if self.wants_update:
                        self.operation = IMatchImage.OP_UPDATE
                    if self.wants_metadata:
                        self.operation = IMatchImage.OP_METADATA
                    if self.wants_delete:
                        self.operation = IMatchImage.OP_DELETE
        else:
            self.operation = IMatchImage.OP_INVALID

    def __repr__(self) -> str:
        return vars(self)

    def __str__(self) -> str:
        return f"{type(self).__name__} (id: {self.id}, filename: {self.filename}, size: {self.size})"

    def add_flat_keyword(self, keyword) -> str:
        clean_keyword = keyword.replace("--", "-")
        clean_keyword = clean_keyword.replace(" ","-")
        clean_keyword = clean_keyword.replace("&","-and-")
        if not clean_keyword in self.flat_keywords:
            self.flat_keywords.add(clean_keyword.lower())
        return clean_keyword
    
    def add_hierarchical_keyword(self, keyword) -> str:
        clean_keyword = keyword.replace("--", "-")
        clean_keyword = clean_keyword.replace(" ","-")
        clean_keyword = clean_keyword.replace("&","-and-")
        if not clean_keyword in self.hierarchical_keywords:
            self.hierarchical_keywords.append(clean_keyword.lower())
        return clean_keyword
    
    def is_image_in_category(self, search_category) -> bool:
        found = False
        for category in self.categories:
            if category['path'] == search_category:
                found = True
                break
        return found
            
    @property
    def is_on_platform(self) -> bool:
        raise NotImplementedError("Subclasses must implement is_on_platform()")
    
    @property
    def camera_info(self) -> str:
        """Standardise a basic way of presenting camera information on a single line"""
        camera_info = []
        try:
            match self.model:
                case "UltraFractal":
                    camera_info.append("Digital image generated in Ultrafractal.")
                case "ScanSnap S1300":
                    camera_info.append("Digitised from a print scanned using a Fujitsu ScanSnap S1300.")
                case other:
                    camera_info.append(self.model)
        except AttributeError:
            pass
        if self.lens.strip() != '':
            camera_info.append(self.lens)

        return " | ".join(camera_info) if len(camera_info) > 0 else ''

    @property
    def shooting_info(self) -> str:
        """Standardise a basic way of presenting shooting information on a single line"""
        shooting_info = []

        try:
            if self.iso != '':
                shooting_info.append(f"ISO {self.iso}")
        except AttributeError:
            pass

        try:
            if self.shutter_speed != '':
                shooting_info.append(f"{self.shutter_speed} sec")
        except AttributeError:
            pass

        try:
            shooting_info.append('f/{0:.3g}'.format(float(self.aperture)))
        except (AttributeError, ValueError):
            pass

        try:
            shooting_info.append(f"{self.focal_length}") 
        except AttributeError:
            pass
           
        return " | ".join(shooting_info) if len(shooting_info) > 0 else ''
   
    @property
    def has_versions(self) -> bool:
        return self.versions is not None
    
    @property
    def is_valid(self) -> bool:
        for attribute in ['title', 'hierarchical_keywords', 'ai_description']:
            try:
                value  = getattr(self, attribute)
                if isinstance(value, list):
                    if len(value) == 0:
                        self.errors.append(f"missing {attribute}")    
                if isinstance(value, str):
                    if value.strip() == '':
                        self.errors.append(f"missing {attribute}")
            except AttributeError as e:
                self.errors.append(f"missing {attribute}")
        genre_ok = False
        try:
            for categories in self.categories:
                splits = categories['path'].split("|")
                if splits[0] == "Image Characteristics" and splits[1] == "Genre":
                    genre_ok = True
        except AttributeError:
            self.errors.append(f"no keywords")
        if not genre_ok:
            self.errors.append(f"missing genre")
        if self.format not in self.controller.allowed_formats:
            self.errors.append("invalid format")
        return len(self.errors) == 0

    @property
    def controller(self):
        if self._controller is None:
            raise ValueError("Controller has not been set")
        else:
            return self._controller

    @controller.setter
    def controller(self, controller):
        self._controller = controller

    @property
    def wants_delete(self) -> bool:
        return self.is_image_in_category(
            im.IMatchUtility.build_category([
                config.ROOT_CATEGORY,
                self._controller.name,
                config.DELETE_CATEGORY
                ])
            )

    @property
    def wants_metadata(self) -> bool:
        return self.is_image_in_category(
            im.IMatchUtility.build_category([
                config.ROOT_CATEGORY,
                self._controller.name,
                config.UPDATE_METADATA_CATEGORY
                ])
            )

    @property
    def wants_update(self) -> bool:
        return self.is_image_in_category(
            im.IMatchUtility.build_category([
                config.ROOT_CATEGORY,
                self._controller.name,
                config.UPDATE_CATEGORY
                ])
            )

        
        
        

