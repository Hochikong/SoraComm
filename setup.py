# -*- coding: utf-8 -*-
# @Time    : 2017/9/1 22:33
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : publib.py
# @Software: PyCharm

from setuptools import setup, find_packages
setup(
    name='stockclib',
    version='0.3',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['neo4j-driver',
                      'bs4',
                      'jieba',
                      'retrying',
                      'requests',
                      'lxml',
                      'selenium',
                      'pymongo',
                      'flask',
                      'tushare'
                      ],

    description='The basic library for Sora',
    author='Hochikong',
    author_email='hochikong@foxmail.com',
    url='http://github.com/hochikong'
)
