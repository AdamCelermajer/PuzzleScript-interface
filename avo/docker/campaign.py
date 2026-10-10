"""Trusted container entry point. Normal campaigns launch directly; isolation probes are an explicit diagnostic."""
import runpy

runpy.run_module('avo.evolve', run_name='__main__')
