import sys
sys.set_int_max_str_digits(0)
def arctan_inv(x, digits):
    # integer arithmetic arctan(1/x) scaled by 10**(digits+10)
    one = 10 ** (digits + 10)
    term = one // x; total = term; x2 = x * x; n = 3; sign = -1
    while term:
        term //= x2
        total += sign * (term // n)
        sign = -sign; n += 2
    return total
def pi_digits(n):
    p = 16 * arctan_inv(5, n) - 4 * arctan_inv(239, n)
    return str(p)[: n + 1]   # '3' followed by n digits
if __name__ == "__main__":
    s = pi_digits(60); print(s)
    assert s.startswith("314159265358979323846264338327950288419716939937510"), s
