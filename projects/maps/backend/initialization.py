from restapi.connectors import celery
# Unused since Auth is not enabled
class Initializer:

    """
    This class is instantiated just after restapi init
    Implement the constructor to add operations performed one-time at initialization
    """

    def __init__(self) -> None:
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

    # This method is called after normal initialization if TESTING mode is enabled
    def initialize_testing_environment(self) -> None:
        pass
