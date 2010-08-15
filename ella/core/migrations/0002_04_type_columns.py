
from south.db import db
from django.db import models

class Migration:

    def forwards(self, orm):
        db.alter_column('core_placement', 'publishable_id', models.ForeignKey(orm['core.Publishable'], null=False))
        db.create_index('core_placement', ['publishable_id'])

#        db.delete_unique('core_placement', ('target_ct_id', 'target_id', 'category_id'))
        db.delete_column('core_placement', 'target_ct_id')
        db.delete_column('core_placement', 'target_id')

    def backwards(self, orm):
        pass
#        db.add_column('core_placement', 'target_ct', models.ForeignKey(orm['contenttypes.ContentType'], null=True))
#        db.add_column('core_placement', 'target_id', models.IntegerField(null=True))
#
#        db.drop_index('core_placement', ['publishable_id'])
#        db.alter_column('core_placement', 'publishable_id', models.IntegerField(null=True))


    models = {
        'contenttypes.contenttype': {
            'Meta': {'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'core.publishable': {
            'Meta': {'app_label': "'core'"},
            '_stub': True,
            'id': ('models.AutoField', [], {'primary_key': 'True'})
        },
    }

