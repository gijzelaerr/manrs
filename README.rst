MANRS benchmarking tool
#######################

This the benchmarking tool for MANRS compliance. Based on publicly available
data it calculates various metrics based on the actions defined in the MANRS
manifesto. The results are then saved in a DataBase for further analysis and
historic status progression.

An API is also available for exposing the stored data.

The tool is written mainly in Python 3.

Further documentation can be found in the `documentation directory <doc/>`__.
Namely you can find:

- `Architecture Documentation <doc/Architecture.rst>`__;
- `Metrics Documentation <doc/Metrics.rst>`__;
- `Installation Instructions <doc/installation.rst>`__;
- `API Documentation <doc/API.rst>`__.

The pdf variants of the documentation were generated using `pandoc <https://pandoc.org/>`__::

    pandoc filename.rst -o filename.pdf
