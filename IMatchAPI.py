import os         # For Windows stuff
import json       # json library
import requests   # See: http://docs.python-requests.org/en/master/
from pprint import pprint
import logging
import sys

logging.getLogger('urllib3').setLevel(logging.INFO) # Don't want this debug level to cloud ours

## Utility class to make the main IMatchAPI class a little less complex
class IMatchUtility:

    @classmethod
    def build_category(cls, path_levels):
        """Build a valid category path from a list of levels"""
        return "|".join(path_levels)

    @classmethod       
    def getID(cls, x):
        """Pull the file id from a {} record where ID is a field"""
        return x['id']

    @classmethod
    def listIDs(cls, x):
        """Given a list of items where one record in the field is ID, return the list of IDs"""
        return list(map(cls.getID, x))
    
    @classmethod
    def prepare_filelist(cls, filelist):
        """Accept an array of image ids, or a single id and format for an IMmatchAPI call"""
        if isinstance(filelist, list):
            return ",".join(map(str, filelist))
        else:
            return f"{filelist}"
            # isinstance failing to detect int when all else says it is. So now we just assume.
            if isinstance(filelist,int):
                f"{filelist}"
                return f"{filelist}"
            else:
                raise TypeError("Filelist argument must be single integer or list of integers.")      
    

class IMatchAPI:
    """Connect to an active IMatch database. Implemented as a Singleton Design pattern."""
    COLLECTION_WRITE_BACK_PENDING = 5
    COLLECTION_BOOKMARKS = 2
    COLLECTION_FLAGS = 10
    COLLECTION_FLAGS_SET = 11               # Checquered flag
    COLLECTION_FLAGS_UNSET = 12             # Red flag
    COLLECTION_FLAGS_NONE = 13
    COLLECTION_DOTS = 30
    COLLECTION_DOTS_RED = 31
    COLLECTION_DOTS_GREEN = 32
    COLLECTION_DOTS_BLUE = 33
    COLLECTION_DOTS_NONE = 34
    COLLECTION_PINS = 50
    COLLECTION_PINS_RED = 51
    COLLECTION_PINS_GREEN = 52
    COLLECTION_PINS_BLUE = 53
    COLLECTION_PINS_NONE = 54
    REQUEST_TIMEOUT = 10                    # Request timeout in seconds

    __auth_token = None # This stores the IMWS authentication token after authenticate() has been called
    __host_url = None
    collection_values = {
        COLLECTION_FLAGS : "Flags",
        COLLECTION_FLAGS_SET : "Flags|Set",
        COLLECTION_FLAGS_UNSET : "Flags|Unset",
        COLLECTION_FLAGS_NONE : "Flags|None",
        COLLECTION_DOTS : "Dots",
        COLLECTION_DOTS_RED : "Dots|Red",
        COLLECTION_DOTS_GREEN : "Dots|Green",
        COLLECTION_DOTS_BLUE : "Dots|Blue",
        COLLECTION_DOTS_NONE : "Dots|None",
        COLLECTION_PINS : "Pins",
        COLLECTION_PINS_RED : "Pins|Red",
        COLLECTION_PINS_GREEN : "Pins|Green",
        COLLECTION_PINS_BLUE : "Pins|Blue",
        COLLECTION_PINS_NONE : "Pins|None",
        }   
    
    FORMAT_AFPHOTO = "AFPHOTO"
    FORMAT_DNG = "DNG"
    FORMAT_JPEG = "JPEG"
    FORMAT_WEBP = "WebP"

    def __init__(self, host_port=50519) -> None:
        """ Authenticate against IMWS and set the __auth_token variable
            to the returned authentication token. We need this for all other endpoints. """
        if IMatchAPI.__auth_token is not None:
            pass
        else:
            # We need to connect to IMatch
            IMatchAPI.__host_url = f"http://127.0.0.1:{host_port}"

            try:
                print(f"IMatchAPI: Attempting connection to IMatch on port {host_port}")
                req = requests.post(IMatchAPI.__host_url + '/v1/authenticate', params={
                    'id': os.getlogin(),
                    'password': '',
                    'appid': ''},
                    timeout=IMatchAPI.REQUEST_TIMEOUT)

                response = json.loads(req.text)

                # If we're OK, store the auth_token in the global variable
                if req.status_code == requests.codes.ok:
                    IMatchAPI.__auth_token = response["auth_token"]
                else:
                    # Raise the exception matching the HTTP status code
                    req.raise_for_status()

                print(f"IMatchAPI: Authenticated to {IMatchAPI.__host_url}")
                return
            except requests.exceptions.ConnectionError as ce:
                logging.error(f"[IMatchAPI] Unable to connect to IMatch on port {host_port}. Please check IMatch is running and the port is correct.\n\nThe full error was {ce}")
                sys.exit(1)
            except requests.exceptions.RequestException as re:
                print(re)
                sys.exit()
            except Exception as ex:
                print(ex)
                sys.exit(1)

    @classmethod
    def get_imatch(cls, endpoint, params):
        """ Generic get function to IMatch. Other functions call this so there is no need for them to repeat
         the main control loop. Ensures the auth_token is not missed as a parameter. """

        params['auth_token'] = cls.__auth_token

        # Easy to miss the leading / so add it as a courtesy
        if endpoint[:1] != "/":
            endpoint = "/" + endpoint

        try:
            req = requests.get(cls.__host_url + endpoint, params, timeout=cls.REQUEST_TIMEOUT)
            response = json.loads(req.text)
            if req.status_code == requests.codes.ok:
                return response
            else:
                req.raise_for_status()
        except requests.exceptions.RequestException as re:
            logging.error(re)
            logging.error(response)
        except Exception as ex:
            logging.error(ex)

    @classmethod
    def post_imatch(cls, endpoint, params):
        """ Generic post function to IMatch. Other functions call this so there is no need for them to repeat
         the main control loop. Ensures the auth_token is not missed as a parameter. """

        params['auth_token'] = cls.__auth_token

        # Easy to miss the leading / so add it as a courtesy
        if endpoint[:1] != "/":
            endpoint = "/" + endpoint

        req = requests.post(cls.__host_url + endpoint, params, timeout=cls.REQUEST_TIMEOUT)
        response = json.loads(req.text)
        if req.status_code == requests.codes.ok:
            return response
        else:
            req.raise_for_status()
        return

    @classmethod
    def assign_category(cls, category, filelist):
        """Assign files to category"""
        params = {}
        params['path'] = category
        params['fileid'] = IMatchUtility().prepare_filelist(filelist)

        try:
            response = cls.post_imatch( '/v1/categories/assign', params)
            if response is not None:
                if response['result'] == "ok":
                    logging.debug(f'Image assigned to {category}')
                    return
            else:
                print("There was an error removing images from the category. Please see message above.")
                sys.exit()
        except requests.exceptions.RequestException as re:
            print(re)
            print(params)
            sys.exit(1)

    @classmethod
    def delete_attributes(cls, set, filelist, params={}, data={}):
        """ Delete attributes for image with id. Assumes attributes only exist once.
         (modification required if multiple instances of attribute sets are to be managed) """

        params['set'] = set
        params['id'] = IMatchUtility().prepare_filelist(filelist)

        tasks = [{
            'op' : "delete",
            'instanceid': [cls.get_attributes(set,filelist)[0]['instanceId']],
        }]

        params['tasks'] = json.dumps(tasks)  # Necessary to stringify the tasks array before sending

        logging.debug(f"Sending instructions : {params}")

        response = cls.post_imatch( '/v1/attributes', params)

        if response['result'] == "ok":
            logging.debug("Success")
        else:
            logging.error("There was an error updating attributes.")
            pprint(response)
            sys.exit(1)

    @classmethod
    def get_application_variable(cls, variable):
        """ Retrieve the named application variable from IMatch (Edit|Preferences|Variables)"""
        params = {}
        params['name'] = variable

        response = cls.get_imatch( '/v1/imatch/appvar', params)
        return response['value']

    @classmethod
    def get_attributes(cls, set, id, params={}):
        """ Return all attributes for a list of file ids. filelist is an array. """

        params['set'] = set
        params['id'] = IMatchUtility().prepare_filelist(id)

        logging.debug(f"Retrieving attributes for {params['id']}")
        response = cls.get_imatch( '/v1/attributes', params)

        # Strip away the wrapping from the result
        results = []
        for attributes in response['result']:
            results.append(attributes['data'][0])
        logging.debug(f"{len(results)} attribute instances retrieved.")
        return results

    @classmethod
    def get_category_info(cls, category, params={}):
        """ Return information about a category"""

        params['path'] = category
        
        logging.debug(f"Retrieving category information for {category}")
        response = cls.get_imatch( '/v1/categories', params)
        return response['categories']

    @classmethod
    def get_file_categories(cls, filelist, params={}):
        """ Return the categories for the list of files """

        params['id'] = IMatchUtility().prepare_filelist(filelist)

        response = cls.get_imatch( '/v1/files/categories', params)
        results = {}
        for file in response['files']:
            logging.debug(file)
            results[file['id']] = file['categories']
        logging.debug(f"{len(results)} images with categories.")
        return results
        
    @classmethod
    def get_categories(cls, path):
        """ Return the requested information all files in the specified category """

        params={}
        params['path'] = path
        params['fields'] = 'files,directfiles'

        logging.debug(f'Retrieving list of files in the {path} category.')
        try:
            response = cls.get_imatch( '/v1/categories', params)
            if len(response['categories']) == 0:
                # This also fires if category does not exist
                logging.debug("0 files found.")
                return []
            else:
                # Get straight to the data if present
                logging.debug(f"{len(response['categories'][0]['files'])} files found.")
                return response['categories'][0]
        except requests.exceptions.RequestException as re:
            print(re)
            print(response)
        except Exception as ex:
            print(ex)


    @classmethod
    def get_categories_children(cls, path):
        """ Return the requested information all child categories the specified category """

        params={}
        params['path'] = path
        params['fields'] = 'children,files,path'

        logging.debug(f'Retrieving list of children categories in the {path} category.')
        response = cls.get_imatch( '/v1/categories', params)
        if len(response['categories']) == 0:
            logging.debug("0 categories found.")
            return []
        else:
            # Get straight to the data if present
            logging.debug(f"{len(response['categories'][0]['children'])} children found.")
            return response['categories'][0]['children']


    @classmethod
    def get_file_metadata(cls, filelist, params={}):
        """ Return details list of file ids """

        params['id'] = IMatchUtility().prepare_filelist(filelist)
        response = cls.get_imatch( '/v1/files', params)
        return response['files']
    
    @classmethod
    def get_master_id(cls, id):
        """ Return the number of the master if one exists """

        params = {}
        params["id"] = id
        params["type"] = "masters"

        response = cls.get_imatch( '/v1/files/relations', params)

        if len(response['files'][0]['masters']) == 1:
            return response['files'][0]['masters'][0]['files'][0]['id']
        else:
            return None
        
    @classmethod
    def get_relations(cls, id):
        """ Return a list of relations for the provided photo id """

        params = {}
        params["id"] = id
        params["type"] = "versions"

        response = cls.get_imatch( '/v1/files/relations', params)
        if len(response['files'][0]['versions']) == 1:
            return response['files'][0]['versions'][0]['files']
        else:
            return None

    @classmethod
    def file_collections(cls, image_id) -> bool:
        """ Returns the collections a file belongs to """

        params = {}
        params["id"] = image_id

        try:       
            response = cls.get_imatch( '/v1/files/collections', params)
            return response['files'][0]['collections']
        except requests.exceptions.RequestException as re:
            print(re)
            print(response)
        except Exception as ex:
            print(ex)

    @classmethod
    def set_attributes(cls, set, filelist, params={}, data={}):
        """ Set attributes for image with id. Assumes attributes only exist once. Will either add or update as needed.
         (modification required if multiple instances of attribute sets are to be managed) """

        params['set'] = set
        params['id'] = IMatchUtility().prepare_filelist(filelist)

        # Can neither assume no attribute instance, or an existing attribute instance. 
        # Check first

        attributes = cls.get_attributes(set, filelist)

        if len(attributes) == 0:
            # No existing attributes, do an add
            logging.debug("Adding attribute row.")
            tasks = [{
                'op' : "add",
                'data' : data
            }]
        else:
            op = 'update'
            logging.debug("Updating existing attribute row.")
            tasks = [{
                'op' : "update",
                'instanceid': [attributes[0]['instanceId']],
                'data' : data
            }]

        params['tasks'] = json.dumps(tasks)  # Necessary to stringify the tasks array before sending

        logging.debug(f"Sending instructions : {params}")

        response = cls.post_imatch( '/v1/attributes', params)

        if response['result'] == "ok":
            logging.debug("Success")
        else:
            logging.error("There was an error updating attributes.")
            pprint(response)
            sys.exit()

    @classmethod
    def set_collections(cls, collection, filelist, op="add", params={}):
        """ Set collections for files."""
        if isinstance(collection, int):
            path = cls.collection_values[collection]
        else:
            path = collection

        params['id'] = IMatchUtility().prepare_filelist(filelist)
            
        tasks = [{
            'op' : op,
            'path' : path
        }]

        params['tasks'] = json.dumps(tasks)  # Necessary to stringify the tasks array before sending

        response = cls.post_imatch( '/v1/collections', params)
        if response is not None:
            if response['result'] == "ok":
                logging.debug("Success")
                return
        else:
            print("There was an error updating the collection. Please see message above.")
            sys.exit()

    @classmethod
    def unassign_category(cls, category, filelist):
        """Remove files from category"""
        params = {}
        params['path'] = category
        params['fileid'] = IMatchUtility().prepare_filelist(filelist)

        response = cls.post_imatch( '/v1/categories/unassign', params)
        if response is not None:
            if response['result'] == "ok":
                logging.debug("Success")
                return
        else:
            print("There was an error removing images from the category. Please see message above.")
            sys.exit()
