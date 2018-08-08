#/usr/bin/env python

import numpy as np

from . import MPI, occupations
comm = MPI.comm
info = MPI.info

kB = 8.61733e-5 # Boltzmann constant (eV/K)

def susceptibility(e, T=1.0, eta=1e-10):
    """Calculate real part of static electronic susceptibility

        chi(q) = 2/N sum[k] [f(k+q) - f(k)] / [e(k+q) - e(k) + i eta].

    The resolution in q is limited by the resolution in k."""

    nk, nk = e.shape

    kT = kB * T
    x = e / kT

    f = occupations.fermi_dirac(x)
    d = occupations.fermi_dirac_delta(x).sum() / kT

    e = np.tile(e, (2, 2))
    f = np.tile(f, (2, 2))

    scale = nk / (2 * np.pi)
    eta2 = eta ** 2
    prefactor = 2.0 / nk ** 2

    def calculate_susceptibility(q1=0, q2=0):
        q1 = int(round(q1 * scale)) % nk
        q2 = int(round(q2 * scale)) % nk

        if q1 == q2 == 0:
            return -prefactor * d

        df = f[q1:q1 + nk, q2:q2 + nk] - f[:nk, :nk]
        de = e[q1:q1 + nk, q2:q2 + nk] - e[:nk, :nk]

        return prefactor * np.sum(df * de / (de * de + eta2))

    calculate_susceptibility.size = 1

    return calculate_susceptibility

def polarization(e, c, T=1.0, i0=1e-10j):
    """Calculate RPA polarization in orbital basis (density-denstiy):

        Pi(q, a, b) = 2/N sum[k, n, m]
            <k+q m|k+q a> <k a|k n> <k n|k b> <k+q b|k+q m>
            [f(k+q, m) - f(k, n)] / [e(k+q, m) - e(k, n) + i0]

    The resolution in q is limited by the resolution in k."""

    if e.ndim == 2:
        e = e[:, :, np.newaxis]

    if c.ndim == 3:
        c = c[:, :, :, np.newaxis]

    nk, nk, nb = e.shape
    nk, nk, no, nb = c.shape # c[k1, k2, a, n] = <k a|k n>

    kT = kB * T
    x = e / kT

    f = occupations.fermi_dirac(x)

    e = np.tile(e, (2, 2, 1))
    f = np.tile(f, (2, 2, 1))
    c = np.tile(c, (2, 2, 1, 1))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    def calculate_polarization(q1=0, q2=0):
        q1 = int(round(q1 * scale)) % nk
        q2 = int(round(q2 * scale)) % nk

        Pi = np.zeros((no, no), dtype=complex)

        for n in range(nb):
            for m in range(nb):
                df = f[q1:q1 + nk, q2:q2 + nk, m] - f[:nk, :nk, n]
                de = e[q1:q1 + nk, q2:q2 + nk, m] - e[:nk, :nk, n]

                cc = c[:nk, :nk, :, n] * c[q1:q1 + nk, q2:q2 + nk, :, m].conj()

                for a in range(no):
                    cca = cc[:, :, a]

                    for b in range(no):
                        ccb = cc[:, :, b].conj()

                        Pi[a, b] += np.sum(cca * ccb * df / (de + i0))

        return prefactor * Pi

    calculate_polarization.size = nb

    return calculate_polarization

def phonon_self_energy(q, e, g2, T=100.0, i0=1e-10j,
        occupations=occupations.fermi_dirac):
    """Calculate phonon self-energy

        Pi(q, nu) = 2/N sum[k] |g(q, nu, k)|^2
            [f(k+q) - f(k)] / [e(k+q) - e(k) + i0]."""

    nk, nk = e.shape
    nQ, nb, nk, nk = g2.shape

    f = occupations(e / (kB * T))

    e = np.tile(e, (2, 2))
    f = np.tile(f, (2, 2))

    scale = nk / (2 * np.pi)
    prefactor = 2.0 / nk ** 2

    sizes, bounds = MPI.distribute(nQ, bounds=True)

    my_Pi = np.empty((sizes[comm.rank], nb), dtype=complex)

    info('Pi(%3s, %3s, %3s) = ...' % ('q1', 'q2', 'nu'))

    for my_iq, iq in enumerate(range(*bounds[comm.rank:comm.rank + 2])):
        q1 = int(round(q[iq, 0] * scale)) % nk
        q2 = int(round(q[iq, 1] * scale)) % nk

        df = f[q1:q1 + nk, q2:q2 + nk] - f[:nk, :nk]
        de = e[q1:q1 + nk, q2:q2 + nk] - e[:nk, :nk]

        chi = df / (de + i0)

        for nu in range(nb):
            my_Pi[my_iq, nu] = prefactor * np.sum(g2[iq, nu] * chi)

            print('Pi(%3d, %3d, %3d) = %9.2e%+9.2ei'
                % (q1, q2, nu, my_Pi[my_iq, nu].real, my_Pi[my_iq, nu].imag))

    Pi = np.empty((nQ, nb), dtype=complex)

    comm.Allgatherv(my_Pi, (Pi, sizes * nb))

    return Pi
