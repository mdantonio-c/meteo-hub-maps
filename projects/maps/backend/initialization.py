from restapi.connectors import celery

# Unused since Auth is not enabled
class Initializer:

    """
    This class is instantiated just after restapi init
    Implement the constructor to add operations performed one-time at initialization
    """

    def __init__(self) -> None:
        self._initialize_thredds_catalog()
        
        c = celery.get_instance()
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_windy",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_windy",
            args=[],
        )
        
        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_seasonal",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_seasonal",
            args=[],
        )

        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_radar",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_radar",
            args=[],
        )

        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_sub_seasonal",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_sub_seasonal",
            args=[],
        )

        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_geoserver_import_ww3",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_geoserver_import_ww3",
            args=[],
        )

        task = c.create_crontab_task(
            name="check_latest_data_and_trigger_thredds_ingestion",
            hour="*",
            minute="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            task="check_latest_data_and_trigger_thredds_ingestion",
            args=[],
        )

    def _initialize_thredds_catalog(self) -> None:
        """THREDDS catalog directories are now initialized at Docker build time."""
        # This method is now a no-op since THREDDS directories are created
        # in the Dockerfile at build time instead of using an init script
        pass

    # This method is called after normal initialization if TESTING mode is enabled
    def initialize_testing_environment(self) -> None:
        pass
