# Generated manually

from django.db import migrations, models


def set_default_links(apps, schema_editor):
    """Set default link for any products with NULL links"""
    Product = apps.get_model('marketplace', 'Product')
    # Update any NULL links to a placeholder URL
    Product.objects.filter(link__isnull=True).update(link='https://example.com')


def reverse_set_default_links(apps, schema_editor):
    """Reverse migration - no action needed"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0005_remove_product_color'),
    ]

    operations = [
        # First, update any NULL links to have a default value
        migrations.RunPython(set_default_links, reverse_set_default_links),
        # Then make link field required by removing null/blank constraints
        migrations.AlterField(
            model_name='product',
            name='link',
            field=models.URLField(help_text='Link to the service platform', max_length=500),
        ),
        # Remove price field
        migrations.RemoveField(
            model_name='product',
            name='price',
        ),
        # Remove condition field
        migrations.RemoveField(
            model_name='product',
            name='condition',
        ),
    ]

