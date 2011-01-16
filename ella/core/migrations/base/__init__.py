class Migration:
    """
    South 0.7+ picking up this as migration, object must be present.
    Ugly monkey/puke patch until upstream fixes migrations for the rest of the world.
    """

    def forwards(self):
        pass

    def backwards(self):
        pass
