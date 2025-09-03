from abc import ABC, abstractmethod
from imatch_image import IMatchImage
import config

class Album(ABC):

    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.images = set()

    @classmethod
    @abstractmethod
    def __repr__(self):
        """Subclasses must implement this."""
        pass

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
    
    def __iter__(self):
        return iter(self.images)
    
    @classmethod
    @abstractmethod
    def __hash__(self):
        """Subclasses must implement this."""
        pass

    
    def add(self, image):
        if not isinstance(image, IMatchImage):
            raise TypeError(f"Attempt to add something other than an image to album: {self.name}")
        
        self.images.add(image)
        image.albums.add(self)
        
    @classmethod
    @abstractmethod
    def load(cls):
        """Subclasses must implement this to load albums from their own source. Return a {} of Album."""
        pass

    
    