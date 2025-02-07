import sys
import logging

import config
import IMatchAPI as im
import quantum

logging.basicConfig(
    stream = sys.stdout,
    level = logging.INFO,
    format = '%(levelname)8s | %(message)s'
    )

class Factory():

    platforms = {
        'quantum' : {
            'image' : quantum.QuantumImage,
            'controller' : quantum.QuantumController,
            'preferred_format' : im.IMatchAPI.FORMAT_WEBP,
            'allowed_formats' : [im.IMatchAPI.FORMAT_WEBP, im.IMatchAPI.FORMAT_JPEG]
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
                cls.platforms[platform]['preferred_format'],
                cls.platforms[platform]['allowed_formats']
            )
        except KeyError:
            logging.error(f"{cls.__name__}.build(platform): '{platform.name}' is an unrecognised platform. Valid options are {cls.platforms.keys()}.")
            sys.exit()
          
if __name__ == "__main__":

    if not sys.version_info >= (3, 10):
        print(f"Python version 3.10 or later required. You are running with version {sys.version_info.major}.{sys.version_info.minor}")
        sys.exit()

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
        print(f"{controller.name}: Gathering images from IMatch.", end='', flush=True)
        count = 0
        try:
            for image_id in im.IMatchAPI.get_categories(im.IMatchUtility.build_category([config.ROOT_CATEGORY,controller.name]))['directFiles']:
                image = Factory.build_image(image_id, controller)
                count += 1
                if count % 10 == 0:
                    print(f' ...{count}', end='', flush=True)
            print()
            print(f"{controller.name}: {controller.stats['total']} images gathered from IMatch to action.")

            controller.classify_images()
            controller.add_images()
            controller.update_images()
            controller.delete_images()
            controller.finalise()
            controller.summarise()
        except TypeError as ex:
            print(ex) 
            print(f"{controller.name}: 0 images gathered from IMatch.")

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
    print("Done.")
    sys.exit(0)


