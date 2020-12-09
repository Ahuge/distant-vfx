from datetime import datetime
import os
import time
import yagmail

from distant_vfx.filemaker import FMCloudInstance
from distant_vfx.video import VideoProcessor
from distant_vfx.config import Config


def _load_config(config_path):
    config = Config()
    config_did_load = config.load_config(config_path)
    if config_did_load:
        return config.data
    return None


CONFIG = _load_config('shotgun_events_config.yml')


# Shotgun constants
SG_SCRIPT_NAME = CONFIG['SG_VERSION_INJECT_NAME']
SG_SCRIPT_KEY = CONFIG['SG_VERSION_INJECT_KEY']

# FileMaker constants
FMP_URL = CONFIG['FMP_URL']
FMP_USERNAME = CONFIG['FMP_USERNAME']
FMP_PASSWORD = CONFIG['FMP_PASSWORD']
FMP_ADMINDB = CONFIG['FMP_ADMINDB']
FMP_USERPOOL = CONFIG['FMP_USERPOOL']
FMP_CLIENT = CONFIG['FMP_CLIENT']
FMP_VERSIONS_LAYOUT = 'api_Versions_form'
FMP_TRANSFER_LOG_LAYOUT = 'api_Transfers_form'
FMP_TRANSFER_DATA_LAYOUT = 'api_TransfersData_form'
FMP_IMAGES_LAYOUT = 'api_Images_form'

# Filesystem constants
THUMBS_BASE_PATH = '/mnt/Projects/dst/post/thumbs'

# Email constants
EMAIL_USER = CONFIG['EMAIL_USERNAME']
EMAIL_PASSWORD = CONFIG['EMAIL_PASSWORD']
EMAIL_RECIPIENTS = CONFIG['FMP_USERPOOL']
EMAIL_EVENTS = []


def registerCallbacks(reg):
    matchEvents = {
        'Shotgun_Version_Change': ['*'],  # look for any version change event
    }
    reg.registerCallback(SG_SCRIPT_NAME,
                         SG_SCRIPT_KEY,
                         inject_versions,
                         matchEvents,
                         None)


def inject_versions(sg, logger, event, args):

    # event_description = event.get('description')
    event_id = event.get('id')
    event_entity = sg.find_one('EventLogEntry', [['id', 'is', event_id]], ['description'])
    event_description = event_entity.get('description')

    # Determine if this is an in house or external vendor version to inject, or not at all
    vendor = _get_vendor(event_description)
    if vendor is None:
        return

    msg = 'Valid injection candidate found for vendor type {vendor} in Event #{id}'.format(vendor=vendor, id=event_id)
    EMAIL_EVENTS.append(msg)
    logger.info(msg)

    # Wait to make sure the entity is fully created and updated
    time.sleep(1)

    # Extract entity data for the event in question
    entity_id = event.get('meta').get('entity_id')
    entity_type = event.get('meta').get('entity_type')

    # Find the version entity in SG and return relevant details
    entity = sg.find_one(entity_type, [['id', 'is', entity_id]], ['code',
                                                                  'description',
                                                                  'published_files',
                                                                  'sg_path_to_movie',
                                                                  'sg_status_list'])  # TODO: get mrx pkg name

    # If the entity can't be found, return.
    if entity is None:
        msg = 'Could not find matching {entity_type} entity with ID {entity_id}. Cannot inject.'.format(
            entity_type=entity_type, entity_id=entity_id)
        logger.error(msg)
        EMAIL_EVENTS.append(msg)
        _send_email()
        return

    # Extract entity data
    description = entity.get('description', '')
    code = entity.get('code', '')
    published_files = entity.get('published_files', '')
    path_to_movie = entity.get('sg_path_to_movie', '')
    status = entity.get('sg_status_list', '')

    # TODO: Parse exr path.

    # Get the package name (varies between ih and ext vendors)
    if vendor == 'ext':
        package = ''  # TODO: Get mrx pkg name - what sg field will this live in?
    else:
        package = 'dst_ih_' + datetime.now().strftime('%Y%m%d')

    # Prep version data for injection to filemaker
    version_dict = {
        'Filename': code,  # TODO: We might want to use the basename of the movie file instead here
        'DeliveryPackage': package,
        'Status': status,
        'DeliveryNote': description,
        'ShotgunID': entity_id,
        'ShotgunPublishedFiles': published_files,
        'ShotgunPathToMovie': path_to_movie
    }

    # Prep transfer log data for injection to filemaker
    package_dict = {
        'package': package,
        'path': ''  # TODO: Add path to package for mrx packages - what sg field will this be?
    }
    filename_dict = {
        'Filename': os.path.basename(path_to_movie),
        'Path': path_to_movie
    }

    # Generate a thumbnail
    thumb_filename, thumb_path = None, None
    try:
        thumb_filename, thumb_path = _get_thumbnail(path_to_movie)
    except Exception as e:
        msg = 'Could not generate thumbnail for version {code}. (error: {exc})'.format(code=code, exc=e)
        logger.error(msg)
        EMAIL_EVENTS.append(msg)

    # Connect to FMP admin DB and inject data
    with FMCloudInstance(host_url=FMP_URL,
                         username=FMP_USERNAME,
                         password=FMP_PASSWORD,
                         database=FMP_ADMINDB,
                         user_pool_id=FMP_USERPOOL,
                         client_id=FMP_CLIENT) as fmp:

        # Inject new version data into versions table
        version_record_id = fmp.new_record(FMP_VERSIONS_LAYOUT, version_dict)
        if not version_record_id:
            msg = 'Error injecting version data (data: {data})'.format(data=version_dict)
            logger.error(msg)
            EMAIL_EVENTS.append(msg)
            _send_email()
            return

        # Inject transfer log data to transfer tables
        # First check to see if package exists so we don't create multiple of the same package
        records = fmp.find_records(FMP_TRANSFER_LOG_LAYOUT, query=[package_dict])
        msg = 'Searching for existing package records (data: {data})'.format(data=package_dict)
        logger.info(msg)
        EMAIL_EVENTS.append(msg)

        if not records:
            # Create a new transfer log record
            transfer_record_id = fmp.new_record(FMP_TRANSFER_LOG_LAYOUT, package_dict)
            transfer_record_data = fmp.get_record(FMP_TRANSFER_LOG_LAYOUT, record_id=transfer_record_id)
            transfer_primary_key = transfer_record_data.get('fieldData').get('PrimaryKey')
            msg = 'Created new transfer record for {package} (record id {id})'.format(
                package=package, id=transfer_record_id)
            logger.info(msg)
            EMAIL_EVENTS.append(msg)

        else:
            transfer_primary_key = records[0].get('fieldData').get('PrimaryKey')
            msg = 'Transfer record for {package} already exists.'.format(package=package)
            logger.info(msg)
            EMAIL_EVENTS.append(msg)

        # Create transfer data records
        filename_dict['Foriegnkey'] = transfer_primary_key  # Foriegnkey is intentionally misspelled to match db field
        filename_record_id = fmp.new_record(FMP_TRANSFER_DATA_LAYOUT, filename_dict)

        if filename_record_id:
            msg = 'Created new transfer data record for version {version} (record id {id}).'.format(
                version=code, id=filename_record_id)
            logger.info(msg)
            EMAIL_EVENTS.append(msg)
        else:
            msg = 'Error creating transfer data record for version {version}.'.format(version=code)
            logger.error(msg)
            EMAIL_EVENTS.append(msg)

        # If we have a thumbnail, inject to image layout
        if thumb_path is None:
            _send_email()
            return

        thumb_data = {
            'Filename': thumb_filename,
            'Path': thumb_path
        }

        img_record_id = fmp.new_record(FMP_IMAGES_LAYOUT, thumb_data)
        if not img_record_id:
            msg = 'Error injecting thumbnail (data: {data})'.format(data=version_dict)
            logger.error(msg)
            EMAIL_EVENTS.append(msg)
            _send_email()
            return

        response = fmp.upload_container_data(FMP_IMAGES_LAYOUT, img_record_id, 'Image', thumb_path)
        record_data = fmp.get_record(layout=FMP_IMAGES_LAYOUT, record_id=img_record_id)
        img_primary_key = record_data.get('fieldData').get('PrimaryKey')

        # Kick off script to process sub-images
        script_res = fmp.run_script(layout=FMP_IMAGES_LAYOUT,
                                    script='call_process_image_set',
                                    param=img_primary_key)

    _send_email()


def _send_email():
    subject, contents = _format_email()
    yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASSWORD)
    yag.send(EMAIL_RECIPIENTS, subject=subject, contents=contents)


def _format_email():
    dt = datetime.now()
    subject = '[DISTANT_API] {} events processed by Shotgun Events at {}'.format(len(EMAIL_EVENTS), dt)
    contents = ''
    for index, event in enumerate(EMAIL_EVENTS):
        line = '[{}]'.format(index) + ': ' + event + '\n\n'
        contents += line
    return subject, contents


def _get_thumbnail(path_to_movie):

    # Get the thumbnail output path
    mov_filename = os.path.basename(path_to_movie)
    mov_basename = os.path.splitext(mov_filename)[0]
    thumb_filename = '0000 ' + mov_basename + '.jpg'  # Naming structure necessary to parse vfx id with current setup
    thumb_dest = os.path.join(THUMBS_BASE_PATH, thumb_filename)

    # Generate thumbnail
    video_processor = VideoProcessor()
    video_processor.generate_thumbnail(path_to_movie, thumb_dest)
    return thumb_filename, thumb_dest


def _get_vendor(event_description):
    ih_phrase = 'to "ihapp" on Version'
    ext_phrase = 'to "extapp" on Version'
    if ih_phrase in event_description:
        return 'ih'
    elif ext_phrase in event_description:
        return 'ext'
    return None
