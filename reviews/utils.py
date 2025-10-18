

def get_stars_for_rating(rating: float) -> str:
    """Returns a string of stars based on the rating."""
    if rating < 0 or rating > 5:
        return ""

    full_stars = int(rating)
    has_half_star = (rating - full_stars) >= 0.5

    # Create full stars
    stars = "⭐" * full_stars

    # Add half star if needed
    if has_half_star:
        stars += "½⭐"

    # Add empty stars to make total of 5
    total_stars_so_far = full_stars + (1 if has_half_star else 0)
    empty_stars_needed = 5 - total_stars_so_far
    stars += "☆" * empty_stars_needed

    return stars