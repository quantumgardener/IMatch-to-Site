import logging

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

    def add(self, image):
        if not isinstance(image, IMatchImage):
            raise TypeError(f"Attempt to add something other than an image to album: {self.name}")
        
        self.images.add(image)
        
