"""Trusted container entry point. Isolation checks always precede model calls."""
import runpy

runpy.run_module('avo.docker.preflight', run_name='__main__')
runpy.run_module('avo.evolve', run_name='__main__')
