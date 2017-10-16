# -*- coding: utf-8 -*-
# @Time    : 2017/9/27 1:08
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : dtSearch.py
# @Software: PyCharm
# 本文件为searchURL函数提供支持

from bs4 import BeautifulSoup, Comment
from retrying import retry
import re
import requests
import jieba


# ---------------------------
industries_url = 'http://www.wedengta.com/rankCommonList/hotIndustry.html'
url_prefix = 'http://www.wedengta.com'
page_url = 'http://www.wedengta.com/stockDetail/%s/news/1.html'


# ---------------------------
# searchURL基础函数板块
# 包含三个主要函数,被searchURL函数所调用：
# 1.searchIndustry
# 2.searchNEWSURL
# 3.genData

# ===========================
# searchIndustry子版块


def get_industryname(line):
    """
    对industry_collec里的每一条数据提取行业名称，被searchIndustry调用
    :param line:见下面的数据：
    <a data-reactid="3" href="/rankCommonList/industryStockList/2020880056.html" target="_blank">
    <div class="c2" data-reactid="4">通信运营</div><div class="c2" data-reactid="5">
    <b class="num_rise2" data-reactid="6">+1.79%</b></div><div class="c3" data-reactid="7">中国联通</div></a>
    :return:行业名称
    """
    tmp = [i for i in line]  # 获取每一行业的具体html段落
    return tmp[0].get_text()  # 返回行业名称


def search_position(lst, item):  # 查找元素位置(修复了bug)
    """
    搜索行业名在行业名列表industry_names中的位置，被searchIndustry调用
    :param lst: 行业名列表
    :param item: 行业名
    :return: 位置的数字
    """
    for i in lst:
        x = ('').join(i.split())
        y = jieba.lcut(x, cut_all=True)
        y = ('').join(y)
        if item in x:
            return lst.index(i)
        elif y in item:
            return lst.index(i)


@retry(stop_max_attempt_number=5)
def searchIndustry(industry):
    """
    查找指定板块的url
    :param industry: 来自网页的json字典的industry项的值，可以考虑使用retry处理异常
    :return: 返回对应板块的url
    """
    all_industry_text = requests.get(industries_url, timeout=10).text
    soup = BeautifulSoup(all_industry_text, 'lxml')
    try:
        industry_collec = soup.find_all(name='a', attrs={'href': re.compile(r'/rankCommonList')})  # 寻找对应不同板块的超链接集合
        industry_names = list(map(get_industryname, industry_collec))  # 所有板块名组成的列表
        position = search_position(industry_names, industry)  # 找到输入所对应的板块的位置
        industry_url = url_prefix + industry_collec[position].get('href')  # 找到板块的url
        return industry_url
    except TypeError:
        return {'error': '查询错误，错误的板块名'}  # 处理输入的板块为错误的情况

# ===========================
# searchNEWSURL子版块


def search_page_id(line):
    """
    对stock_collec下的每一条数据进行提取股票名，被searchNEWSURL调用
    :param line: 见下面的数据：
    <a data-reactid="3" href="/stockDetail/0001000020/marketQuotation.html" target="_blank">
    <div class="c1" data-reactid="4">深华发Ａ</div><div class="c2" data-reactid="5">
    <b class="num" data-reactid="6">停牌</b></div><div class="c3" data-reactid="7">
    <b class="num_stop2" data-reactid="8">停牌</b></div><div class="c4" data-reactid="9">
    <b class="num" data-reactid="10">19.12</b>
    </div><div class="c5" data-reactid="11"><b class="num" data-reactid="12">0.90%</b></div></a>
    :return:
    """
    tmp = [i for i in line]
    return tmp[0].get_text()


@retry(stop_max_attempt_number=5)
def searchNEWSURL(industry_url, stock_name):
    """
    根据searchIndustry返回的url和用户输入的股票名返回股票的新闻首页url
    :param industry_url: 一个url，来自searchIndustry
    :param stock_name: 来自网页返回的json字典的stock_name项的值
    :return: 返回股票对应新闻的首页url
    """
    stocks_within_industry = requests.get(industry_url, timeout=10).text
    soup = BeautifulSoup(stocks_within_industry, 'lxml')
    stock_collec = soup.find_all(name='a', attrs={'href': re.compile(r'/stockDetail')})
    stock_names = list(map(search_page_id, stock_collec))  # 该板块下所有股票
    try:
        stock_position = search_position(stock_names, stock_name)  # 查找股票位置!!!!!
        raw_stock_url = stock_collec[stock_position].get('href')  # 查找该股票的行情页面url
        stock_page_id = raw_stock_url.split('/')[2]  # 提取页面的id
        stock_url = page_url % stock_page_id  # 根据模版制作新闻页面的url
        return stock_url
    except TypeError:
        return {'error': '查询错误，错误的股票名'}  # 处理输入的股票名为错误的情况

# ===========================
# genData子版块


def get_stock_number(page_text):
    """
    使用page_text转换为soup对象然后返回股票代码，被genData调用
    :param page_text: 从requests返回的text数据
    :return: 字符串的股票代码
    """
    soupobj = BeautifulSoup(page_text, 'lxml')
    block = soupobj.find(attrs={'class': 'num'})
    return block.get_text()


def span_strip(lines):
    """
    因为basic_info_query函数里的theme_list的数据是纯文本，因此去掉HTML标签要用strip,被basic_info_query调用
    :param lines:
    :return:
    """
    tmp = [i.lstrip('<span>') for i in lines]
    tmp = [i.rstrip('</span>') for i in tmp]
    return tmp


def basic_info_query(stock_url):  # 根据爬取的股票对应的网页id获取股票基本信息
    """
    输入一个股票的新闻url，自动提取基本信息和关联主题，可能需要retry，被genData调用
    :param stock_url: 来自searchNEWSURL的url
    :return: 返回一个基本信息列表
    """
    uid = stock_url.split('/')[-3]  # 从url提取id
    url_template = 'http://www.wedengta.com/stockDetail/%s/intro.html'
    url = url_template % uid
    page = requests.get(url, timeout=10).text
    # 获取基本信息
    soupobj = BeautifulSoup(page, 'lxml')
    intro_data = soupobj.find(attrs={'class': 'data_list'})
    tmp = [i for i in intro_data]   # 把intro_data分拆成多条数据
    tmp = [x for x in tmp if x != '\n']  # 过滤掉没用的数据
    result = []
    for i in tmp:
        result.append((i.span.get_text(), i.strong.get_text()))  # 把tmp的数据提取出来，span部分为键，strong部分为值
    result = dict(result)   # 转换为字典

    # 提取关联主题
    comments = soupobj.findAll(text=lambda text: isinstance(text, Comment))
    comments = [comment.extract() for comment in comments]  # 获得注释
    themes = [i for i in comments if 'main_title main_title_strong bdb' in i]  # 提取关联主题板块
    theme_list = [i for i in themes[0].split() if 'span' in i]  # 拆分主题为列表数据
    theme_list = span_strip(theme_list)  # 去掉两边的HTML标签
    result['themes'] = theme_list
    return result


@retry(stop_max_attempt_number=5)
def genData(stock_url):
    """
    根据新闻URL获取股票id和基本信息，需要retry防止数据爬取失败
    :param stock_url: 来自searchNEWSURL的url
    :return: 基本的数据成分，需要flask端补上user的值
    """
    page_text = requests.get(stock_url).text
    stock_number = get_stock_number(page_text)
    data = basic_info_query(stock_url)
    return {'stock_id': stock_number, 'url': stock_url, 'data': data, 'user': 'Empty'}
