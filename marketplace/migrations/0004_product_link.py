# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0003_alter_subcategory_slug'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='link',
            field=models.URLField(blank=True, help_text='Link to buy the product', max_length=500, null=True),
        ),
    ]

