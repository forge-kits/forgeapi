class Layout:
    """Fixed project directory layout.

    These paths are conventions, not settings: ``Core``, the generators
    (``make:*``) and the CLI all rely on them, relative to the project root.
    """

    models_dir = "database/models"
    controllers_dir = "app/controllers"
    schemas_dir = "app/schemas"
    listeners_dir = "app/listeners"
    policies_dir = "app/policies"
    jobs_dir = "app/jobs"
    observers_dir = "app/observers"
    providers_dir = "app/providers"
    commands_dir = "app/commands"
    mail_dir = "app/mail"
    seeds_dir = "database/seeds"
    #: Default location of the scheduler definition; ``config/scheduler.py`` may point elsewhere.
    schedule_file = "schedule.py"


layout = Layout()
