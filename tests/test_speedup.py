"""S9b: the fast optimizer path must give the same numbers as the plain path.

- ReducedSystem assembles exactly triu(K[free][:, free]) (bitwise: same summation order).
- PardisoSPD (analysis once, numeric factorization per call) solves to round-off.
- The element energies from the per-case product match the original einsum.
"""

import numpy as np
import pytest
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve

from morphic import fe, topopt
from tests.test_two_load_cases import small_bracket
from morphic.domain import build_domain


@pytest.fixture(scope="module")
def prob():
    dom = build_domain(small_bracket(), "fdm", 1.2, cap=2500)
    return dom.topopt_problem()


def test_reduced_system_equals_sliced_upper_triangle(prob):
    rng = np.random.default_rng(3)
    Ee = prob.modulus(rng.uniform(0.01, 1.0, prob.mesh.nel))
    K = prob.assembler.assemble(Ee)
    ref = sp.triu(K[prob.free_dofs][:, prob.free_dofs], format="csr")
    ref.sort_indices()
    got = prob.reduced.matrix(Ee)
    assert np.array_equal(got.indptr, ref.indptr)
    assert np.array_equal(got.indices, ref.indices)
    assert np.array_equal(got.data, ref.data)  # bitwise


@pytest.mark.skipif(not fe.HAVE_PARDISO, reason="PyPardiso not installed")
def test_pardiso_spd_matches_direct_solve_over_several_designs(prob):
    rng = np.random.default_rng(4)
    for _ in range(3):  # the analysis is reused; the numbers must still be right each time
        x = rng.uniform(0.01, 1.0, prob.mesh.nel)
        U, ce, _ = prob.analyze(x)
        K = prob.assembler.assemble(prob.modulus(x))
        Kff = K[prob.free_dofs][:, prob.free_dofs].tocsc()
        Uref = spsolve(Kff, prob.loads[prob.free_dofs])
        assert np.abs(U[prob.free_dofs] - Uref).max() <= 1e-10 * np.abs(Uref).max()
        ue = U[prob.mesh.edof]
        ce_ref = np.einsum("eac,ab,ebc->ec", ue, prob.KE_unit, ue)
        assert np.abs(ce - ce_ref).max() <= 1e-10 * np.abs(ce_ref).max()  # u K u cancels: round-off ~1e-12


def test_kmp_blocktime_is_set_before_mkl_loads():
    import os

    import morphic  # noqa: F401

    assert os.environ.get("KMP_BLOCKTIME") is not None
