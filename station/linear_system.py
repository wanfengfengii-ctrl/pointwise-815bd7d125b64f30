from fractions import Fraction


def solve_unique_system(coefficients, right_hand_sides):
    """Solve A X = B over the rationals, with B supplied by rows."""
    size = len(coefficients)
    if len(right_hand_sides) != size or any(len(row) != size for row in coefficients):
        raise ValueError('expected square coefficients and matching right-hand sides')
    if size == 0:
        return ()
    width = len(right_hand_sides[0])
    if any(len(row) != width for row in right_hand_sides):
        raise ValueError('right-hand sides must form a rectangle')
    augmented = [
        [Fraction(value) for value in left] + [Fraction(value) for value in right]
        for left, right in zip(coefficients, right_hand_sides)
    ]
    for column in range(size):
        pivot = next((row for row in range(column, size) if augmented[row][column]), None)
        if pivot is None:
            raise ValueError('system does not have a unique solution')
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [value - factor * basis
                                  for value, basis in zip(augmented[row], augmented[column])]
    return tuple(tuple(row[size:]) for row in augmented)
