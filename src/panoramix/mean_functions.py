from functools import reduce
from math import gcd

def power_mean(order):
    match order:
        case 0:         return lambda vlist: reduce(lambda x, y: x*y, vlist)**(1/len(vlist))
        case '+inf':    return lambda vlist: max(vlist)
        case '-inf':    return lambda vlist: min(vlist)
        case _:         return lambda vlist: ((1/len(vlist))*sum(map(lambda x: x**order, vlist)))**(1/order)

def sum_frac(x, y):
    (a, b), (c, d) = x, y
    pgcd = gcd(b, d)
    ppcm = b*d//pgcd
    numerator = a*(d//pgcd) + c*(b//pgcd)
    denominator = ppcm
    return numerator, denominator


def power_mean_rationnal(order : int):
    compute = lambda x: x[0]/x[1]
    mult = lambda x, y: (x[0]*y[0], x[1]*y[1])
    exp_inv = lambda x, e: compute(x)**(1/e)
    exp = lambda x, e: exp_bis((x[1], x[0]), -e) if e < 0 else exp_bis(x, e)
    exp_bis = lambda x, e: (x[0]**e, x[1]**e)
    big_sum = lambda liste: reduce(lambda x, y: sum_frac(x, y), liste)

    match order:
        case 0:         return lambda vlist: exp_inv(reduce(lambda x, y: mult(x, y), vlist), len(vlist))
        case '+inf':    return lambda vlist: max(map(lambda x: compute(x), vlist))
        case '-inf':    return lambda vlist: min(map(lambda x: compute(x), vlist))
        case _:         return lambda vlist: exp_inv(mult((1, len(vlist)), big_sum(map(lambda x: exp(x, order), vlist))), order)

def quasi_arithmetic_mean(func, inverse_func):
    return lambda vlist: inverse_func((1/len(vlist))*sum(map(lambda x: func(x), vlist)))

if __name__ == '__main__':
    values = [(1, 7), (5, 7), (6, 13)]
    test = power_mean_rationnal(-1)
    print(test(values))
    test2 = power_mean(-1)
    print(test2(list(map(lambda x: x[0]/x[1], values))))