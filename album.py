import json
import logging
import os
import sys

from imatch_image import IMatchImage

class Album():

    def __init__(self, name, id, description):
        self.name = name
        self.id = id
        self.description = description

        self.images = set()

    def __repr__(self):
        return f'{self.__class__.__name__}: {self.name} (id: {self.id} images:{len(self.images)}), {self.description} '

    def __len__(self):
        return len(self.images)
    
    # Implementing comparison methods for sorting
    def __lt__(self, other):
        return self.name < other.name

    def __le__(self, other):
        return self.name <= other.name

    def __gt__(self, other):
        return self.name > other.name

    def __ge__(self, other):
        return self.name >= other.name

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return self.name != other.name
    
    def __hash__(self):
        return hash((self.id, self.name)) 
    
    def add(self, image):
        if not isinstance(image, IMatchImage):
            raise TypeError(f"Attempt to add something other than an image to album: {self.name}")
        
        self.images.add(image)
        
    @classmethod 
    def load(cls, controller):
        data_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),'data.json')

        try:
            with open(data_file, "r") as file:
                data = json.load(file)

            albums = {}
            for album in data[controller]['albums']:
                albums[album['name']] = Album(album['name'], album['id'], album['description'])

        except json.decoder.JSONDecodeError as e:
            logging.error(f"{controller}: Unexpected error loading json file : {data_file}")
            logging.error(f"{controller}: {e}")
            sys.exit(1)
        except FileNotFoundError:
            logging.error(f"{controller}: Unable to create albums. JSON file not found: {data_file}")
            sys.exit(1)
        except KeyError:
            logging.error(f"{controller}: Unable to create albums. Data missing from: {data_file}")
            sys.exit(1)

        return albums