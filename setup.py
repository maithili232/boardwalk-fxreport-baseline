from setuptools import setup, find_packages

setup(
    name="fxreport",
    version="0.3.1",
    description="Weekly EUR exchange rate summaries from the Frankfurter API",
    packages=find_packages(exclude=["tests"]),
    install_requires=["requests>=2.20", "python-dateutil>=2.7"],
    python_requires=">=3.7",
    entry_points={"console_scripts": ["fxreport=fxreport.cli:main"]},
)
