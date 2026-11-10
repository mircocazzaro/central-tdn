from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogapp', '0006_ontology_template'),
    ]

    operations = [
        migrations.AlterField(
            model_name='endpoint',
            name='url',
            field=models.CharField(max_length=500),
        ),
    ]
