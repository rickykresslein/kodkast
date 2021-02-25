import peewee
import os

db_name = 'kodkast.db'
db_dir = os.path.join(os.path.expanduser('~'),'.kodkast')
if not os.path.isdir(db_dir):
    os.makedirs(db_dir)
db_path = os.path.join(db_dir, db_name)
database = peewee.SqliteDatabase(db_path)

class PodcastDB(peewee.Model):
    """
    A database of podcast titles, urls, and images.
    """    
    title = peewee.CharField()
    url = peewee.CharField()
    image = peewee.CharField()
    rendered = peewee.CharField(default="")

    class Meta:
        database = database

class EpisodeDB(peewee.Model):
    """
    A database of podcast ids, episode titles, publish dates, urls, images, and durations
    """
    podcast = peewee.ForeignKeyField(PodcastDB)
    title = peewee.CharField()
    pub_date = peewee.DateField()
    url = peewee.CharField()
    image = peewee.CharField()
    bookmark = peewee.IntegerField()

    class Meta:
        database = database
