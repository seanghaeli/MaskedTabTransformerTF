from setuptools import setup, find_packages

setup(
    name="maskedtabtransformertf",
    packages=find_packages(),
    version="0.0.1",
    license="MIT",
    description="Maksed Tab Transformer - TensorFlow",
    author="Antons Ruberts",
    author_email="rubertant@gmail.com",
    keywords=[
        "artificial intelligence",
        "transformers",
        "attention mechanism",
        "tabular data",
    ],
    install_requires=[
        "tensorflow>=2.6.2",
        "pandas>=1.1.1",
        "numpy>=1.19.5",
        "tqdm>=4.64.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
    ],
)
