# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0004_product_link'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='color',
        ),
    ]

