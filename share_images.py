import sys
import logging
import pprint
import time

import config
import IMatchAPI as im
import flickr
import quantum
from utilities import print_clear


logging.basicConfig(
    stream = sys.stdout,
    level = logging.INFO,
    format = '[%(levelname)-7s] %(message)s'
    )

class Factory():

    platforms = {
        'quantum' : {
            'image' : quantum.QuantumImage,
            'album' : quantum.QuantumAlbum,
            'controller' : quantum.QuantumController,
            'preferred_format' : im.IMatchAPI.FORMAT_WEBP,
            'allowed_formats' : [im.IMatchAPI.FORMAT_WEBP, im.IMatchAPI.FORMAT_JPEG]
        },
        'flickr' : {
            'image' : flickr.FlickrImage,
            'album' : flickr.FlickrAlbum,
            'controller' : flickr.FlickrController,
            'preferred_format' : im.IMatchAPI.FORMAT_JPEG,
            'allowed_formats' : [im.IMatchAPI.FORMAT_JPEG]
        },    
    }

    def __init__(self) -> None:
        pass
        
    @classmethod
    def build_image(cls, id, platform): 
        try:
            return cls.platforms[platform.name]['image'](id, platform)
        except KeyError:
            logging.error(f"{cls.__name__}.build(platform): '{platform.name}' is an unrecognised platform. Valid options are {cls.platforms.keys()}.")
            sys.exit()
        
    @classmethod
    def build_controller(cls, platform):
        try:
            return cls.platforms[platform]['controller'](
                platform,
                cls.platforms[platform]['album'],
                cls.platforms[platform]['preferred_format'],
                cls.platforms[platform]['allowed_formats']
            )
        except KeyError:
            logging.error(f"{cls.__name__}.build(platform): '{platform.name}' is an unrecognised platform. Valid options are {cls.platforms.keys()}.")
            sys.exit()
          
if __name__ == "__main__":

    start_time = time.time()

    # Retreive the complete list of Socials files from IMatch for all known
    # platforms. Within IMatch, files are in the Socials|{platform} category
    # or subcategories.

    images = []             # main image store
    platform_controllers = set()

    im.IMatchAPI()             # Perform initial connection

    # Gather all image information for the specified platforms
    if len(sys.argv[1:]) > 0:
        for platform in sys.argv[1:]:
            platform_controllers.add(Factory.build_controller(platform))
    else:
        # Do the lot
        for platform in Factory.platforms.keys():
            platform_controllers.add(Factory.build_controller(platform))

    for controller in platform_controllers:
        print( "--------------------------------------------------------------------------------------")
        try:
            images = im.IMatchAPI.get_categories(im.IMatchUtility.build_category([config.ROOT_CATEGORY,controller.name]))['directFiles']
        except TypeError:
            logging.error(f"{controller.name}: Root socials category missing: {im.IMatchUtility.build_category([config.ROOT_CATEGORY,controller.name])}")
            sys.exit(1)
        count = 0
        max_images = len(images)
        try:
            for image_id in images:
                image = Factory.build_image(image_id, controller)
                count += 1
                print(f"{controller.name}: Gathering images from IMatch [{count:2.0f} of {max_images}]", end='\r')
            print_clear(f"{controller.name}: {controller.stats['total']} images gathered from IMatch to action")

            controller.classify_images()
            controller.add_images()
            controller.update_images()
            controller.delete_images()
            controller.finalise()
            controller.summarise()
        except TypeError as ex:
            print(ex) 
            sys.exit(1)

    # stats = {}
    # for controller in platform_controllers:
    #     platform_stats = controller.stats
    #     for stat in platform_stats:
    #         try:
    #             stats[stat] += platform_stats[stat]
    #         except KeyError:
    #             stats[stat] = platform_stats[stat]
            
    # print( "--------------------------------------------------------------------------------------")
    # print(f"Final summary of images processed")
    # for val in stats.keys():
    #     print(f"-- {stats[val]} {val} images")
    
    print("--------------------------------------------------------------------------------------")
    print(f"Done in {time.time()-start_time:.2f}s")
    sys.exit(0)


