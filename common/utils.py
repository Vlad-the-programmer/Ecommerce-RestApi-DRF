import logging
import uuid
from typing import Type, Optional
from django.utils.text import slugify

from common.models import CommonModel

modelType = Type[CommonModel]

logger = logging.getLogger(__name__)


def check_slug_unique(model: modelType, slug: str, instance: CommonModel = None) -> bool:
    """
    Check if the slug is unique for the given model.

    Args:
        model: The model to check the slug for (e.g. Product).
        slug: The slug to check.
        instance: The current instance to exclude from the check.

    Returns:
        True if the slug is unique for the given model.
        False otherwise.
    """
    queryset = model.objects.filter(slug=slug)
    if instance and instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    return not queryset.exists()


def generate_unique_slug(model: modelType, instance: CommonModel, fields_to_slugify: list[str]) -> Optional[str]:
    """
    Generate a unique slug for the given model instance.

    Args:
        model: The model to generate a slug for (e.g. Product).
        instance: The object instance to generate a slug for.
        fields_to_slugify: List of fields to use for generating the slug.

    Returns:
        A unique slug for the given model.
        None if an AttributeError is raised due to model missing fields from fields_to_slugify list.
    """
    try:
        # Get field values for slug generation
        field_values = []
        for field in fields_to_slugify:
            try:
                value = getattr(instance, field)
                if callable(value):
                    value = value()  # Handle methods like get_category_display
                field_values.append(str(value))
            except AttributeError:
                logger.warning(f"Field '{field}' not found on {instance}, skipping")
                continue

        # If no valid fields found, return None
        if not field_values:
            logger.warning(f"No valid fields found for slug generation: {fields_to_slugify}")
            return None

        # Generate base slug
        base_slug = slugify("-".join(field_values))

        # If base slug is empty (e.g., all fields were empty), use a fallback
        if not base_slug:
            logger.warning("Generated base slug is empty")
            return None

        # Ensure unique slug
        slug = base_slug
        counter = 1

        while not check_slug_unique(model, slug, instance):
            slug = f"{base_slug}-{counter}"
            counter += 1

            # Safety check to prevent infinite loops
            if counter > 100:
                # Use UUID as fallback for extremely rare cases
                unique_part = uuid.uuid4().hex[:8]
                slug = f"{base_slug}-{unique_part}"
                logger.warning(f"Used UUID fallback for slug: {slug}")
                break

        logger.info(f"Generated unique slug: {slug} for {instance}")
        return slug

    except Exception as e:
        logger.error(f"Error in generate_unique_slug: {e}")
        return None