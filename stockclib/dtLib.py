# -*- coding: utf-8 -*-
# @Time    : 2017/9/28 14:00
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : dtLib.py
# @Software: PyCharm
# 本文件为openTransaction,compareURLs,updateNEWSandURLs提供支持

from bs4 import BeautifulSoup
from functools import reduce
from datetime import datetime
from retrying import retry
from concurrent.futures import ThreadPoolExecutor
import re
import requests
import jieba

# -------------------------
# 初始化
pool = ThreadPoolExecutor(max_workers=10)
url_prefix = 'http://www.wedengta.com'
news_index = 'http://www.wedengta.com/stockDetail/0001000050/news/%d.html'

# -------------------------
# 公共函数


@retry(stop_max_attempt_number=4)
def generalGet(urls, soup=False):
    """
    一个包含retry功能的通用爬取函数，代替requests的get函数,若超过指定的重试次数，
    则抛出异常ConnectionError: None: Max retries exceeded with url: / (Caused by None)
    :param urls: 一个包含一条或多条url的列表
    :return: 返回一个包含url get回来的原始text对象的列表
    """
    request_instance = [pool.submit(requests.get, url=each_url, timeout=10).result() for each_url in urls]
    request_text = [instance.text for instance in request_instance]
    if soup:
        request_soup = [BeautifulSoup(text, 'lxml') for text in request_text]
        return request_soup
    else:
        return request_text


def get_urls(page_text):
    """
    对来自generalGet的单条原始文本进行处理获取页面的全部新闻的url
    :param page_text: request_text中的任一元素
    :return: 返回url列表
    """
    url_list = re.findall(
        r"(?<=href=\").+?(?=\")|(?<=href=\').+?(?=\')",
        page_text)
    return url_list  # 返回的url,每次暂停操盘后重启爬虫都要爬取当前url和后2页的全部带情绪的数据


def generalFilter(urls, cond, ops):
    """
    通过字符串对url列表进行过滤或者修改
    :param urls: 任意一组url组成的列表
    :param cond: 字符串条件
    :param ops: 1.select:选取含cond的urls返回 2.delete：删除含cond的urls，返回剩余urls 3.add：在每条url头部添加cond
    :return: 过滤后的列表
    """
    if ops == 'select':
        return [each for each in urls if cond in each]
    if ops == 'delete':
        return [each for each in urls if cond not in each]
    if ops == 'add':
        return [cond+each for each in urls]


def generalCacheGet(query):
    """
    对数据库的查询结果的各个url进行页面爬取并返回未经过滤的和已经过滤的url列表，数据直接在query的基础上追加news和cache部分
    :param query: 查询自数据库并经RPC服务器处理的数据，如下：
    [{'stock_id': '000050',
      'url': 'http://www.wedengta.com/stockDetail/0001000050/news/1.html'},
     {'stock_id': '000997',
      'url': 'http://www.wedengta.com/stockDetail/0001000997/news/1.html'}]
    :return: 返回一个复杂列表
    """
    urls = [row['url'] for row in query]  # 顺序不变
    texts = generalGet(urls)
    cacheURLs = [get_urls(text) for text in texts]  # 包含每支股票的cacheURL的列表
    for index in range(len(query)):
        query[index]['cache'] = generalFilter(generalFilter(cacheURLs[index], '/newsDetail/', 'select'),
                                              url_prefix, 'add')  # 选取新闻并添加url_prefix
        query[index]['news'] = generalFilter(query[index]['cache'], '_9_1', 'delete')  # 直接通过url特征过滤‘数据日报’
    return query


# --------------------------
# 页面分析函数


def get_sentiment(soupobj):
    """
    从页面的soup对象中提取情绪信息
    :param soupobj: text经过BS4处理的结果
    :return: 返回一个情绪字符串
    """
    data = set(
        soupobj.find(
            attrs={
                'class': 'news_tag'}).get_text().split('\n'))
    data.remove('')
    attibute = list(data)[0]
    diffcase = {'利好': 'positive', '买入': 'strong buy', '强烈利空': 'strong neg',
                '增持': 'buy', '中性': 'neutral', '利空': 'negative', '强烈利好': 'strong pos'}
    return diffcase[attibute]


def get_data_and_source(soupobj):
    """
    从页面的soup对象中提取发布日期与来源，若无来源说明，则设置为N/A
    :param soupobj: text经过BS4处理的结果
    :return: 返回包含来源与发布日期的字典
    """
    data = soupobj.find(attrs={'class': 'news_info'})
    result = data.get_text()
    result = result.split(' ', 1)  # 提取出原始数据列表

    if result[0] != '':  # 有些公告是没有来源的
        msg_source_tmp = jieba.lcut(result[0])
        msg_source = reduce(lambda x, y: x + y, msg_source_tmp[2:])  # 获得来源
    else:
        msg_source = 'N/A'

    msg_time = jieba.lcut(result[1])
    date_tmp = msg_time[3:8]
    time_tmp = msg_time[9:]
    date = reduce(lambda x, y: x + y, date_tmp)  # 获得消息发布的日期
    time = reduce(lambda x, y: x + y, time_tmp)  # 获得消息发布的具体时间

    return {'source': msg_source, 'date': date, 'time': time}


def get_abstract(soupobj):
    """
    从页面的soup对象中提取摘要内容
    :param soupobj: text经过BS4处理的结果
    :return: 摘要文本
    """
    return (soupobj.find(attrs={'name': 'description'})['content']).strip()


def get_content(soupobj):
    """
    从页面的soup对象中提取正文
    :param soupobj: text经过BS4处理的结果
    :return: 正文文本
    """
    tmp = []
    for i in soupobj.find_all('p'):
        tmp.append(i)
    tmp = [i.get_text() for i in tmp]  # 提取纯文本
    tmp.pop()  # 删掉股票灯塔的Copyright
    return tmp  # 返回的是一个列表，每一个段落都带\r或者\rn,方便打印出来


def count_day_delta(soupobj):
    """
    通过获取当前页面的日期，和程序检测的当前时间计算时间差，因为要根据时间差爬取近日的页面
    :param soupobj: text经过BS4处理的结果
    :return: 日期差值
    """
    msg_source = get_data_and_source(soupobj)
    raw_that_day = msg_source['date']
    that_day = datetime.strptime(raw_that_day, '%Y-%m-%d')
    today = datetime.now()
    delta = (today - that_day).days
    return delta


def analysisPage(soupobj):
    """
    把每个页面的soup对象提取分别提取一些数据：标题、情绪、来源、摘要、原文，调用上面的一系列get函数
    :param soupobj:
    :return: 返回字典
    """
    if count_day_delta(soupobj) <= 2:
        try:   # 如果页面不带情绪，则放弃这条新闻
            title = soupobj.h3.get_text()
            sentiment = get_sentiment(soupobj)
            msg_source = get_data_and_source(soupobj)
            abstract = get_abstract(soupobj)
            # content = get_content(soupobj) 有时原文是图片的话就要由客户端识别了
            return {'title': title, 'sentiment': sentiment, 'msg_source': msg_source, 'abstract': abstract}
            #'content': content}
        except Exception:  # 处理不带情绪的页面
            pass
    else:
        pass


# ----------------------
# 数据库读写函数

# ======================
# 对cache_url进行首次插入或更新


def single_initinsert(stock, collection):
    """
    单条插入函数，被paraInsertCache调用
    :param stock: 单条的ndata内部元素
    :param collection: stock_url集合
    :return:
    """
    collection.insert_one({'stock_id': stock['stock_id'], 'cache_urls': stock['cache']})


def paraInsertCache(data, collection):
    """
    使用多线程对cache_urls进行插入
    :param data: query的处理结果
    :param collection: 指定的表
    :return:
    """
    for stock in data:
        pool.submit(single_initinsert, stock=stock, collection=collection)


def single_update(stock, collection):
    """
    单条更新函数，用于更新cache_urls
    :param stock: 单条的afterfilter内部元素
    :param collection: stock_url集合
    :return:
    """
    collection.update_one({'stock_id': stock['stock_id']}, {'$set': {'cache_urls': stock['cache']}})


def paraUpdateCache(data, collection):
    """
    使用多线程对cache_urls进行更新
    :param data: afterfilter数据
    :param collection: stock_url集合
    :return:
    """
    for stock in data:
        pool.submit(single_update, stock=stock, collection=collection)

# =====================
# 多线程新闻详情的插入与扩展


def single_insert(stock, collection):
    """
    对单条股票数据的新闻进行写入（第一次初始化交易系统时使用）
    :param stock: 单条的ndata内部元素
    :param collection: stock_news集合
    :return:
    """
    collection.insert_one({'stock_id': stock['stock_id'], 'news_content': stock['news_content']})


def paraInsert(data, collection):
    """
    多线程写入数据库
    :param data: ndata
    :param collection: stock_news集合
    :return:
    """
    for stock in data:
        pool.submit(single_insert, stock=stock, collection=collection)


def single_extend(stock, collection):
    """
    对单条股票数据的新闻进行追加，把旧数据追加到新数据后面
    :param stock: 单条的ndata内部元素
    :param collection: stock_news集合
    :return:
    """
    query_result = collection.find_one({'stock_id': stock['stock_id']})
    newscontent = stock['news_content']
    if query_result:
        oldnews = query_result['news_content']
    else:
        oldnews = []
    if len(oldnews) > 0:
        newscontent.extend(oldnews)
        collection.update_one({'stock_id': stock['stock_id']}, {'$set': {'news_content': newscontent}})
    else:
        collection.insert_one({'stock_id': stock['stock_id'], 'news_content': stock['news_content']})


def paraExtend(data, collection):
    """
    多线程写入
    :param data: ndata
    :param collection: stock_news集合
    :return:
    """
    for stock in data:
        pool.submit(single_extend, stock=stock, collection=collection)

# -----------------------
# 多线程爬取新闻


def single_getnews(stock):
    """
    对data里的每一条股票详细数据的news列表进行爬取
    :param stock: data里的单一元素
    :return: 更新后的stock
    """
    soups = generalGet(stock['news'], soup=True)
    news_content = [analysisPage(i) for i in soups]
    news_content = [i for i in news_content if i != None]
    if count_day_delta(soups[-1]) < 2:  # 如果第二页有前两天的新闻，就翻页爬取
        page_index = 2
        newpage = generalGet([news_index % page_index])
        new_urls = generalFilter(
            generalFilter(generalFilter(get_urls(newpage[0]), '/newsDetail/', 'select'),
                          '_9_1', 'delete'), url_prefix, 'add')
        newpage_news = generalGet(new_urls, soup=True)
        only_twodays_ago = [analysisPage(news) for news in newpage_news]
        only_twodays_ago = [news for news in only_twodays_ago if news != None]
        news_content.extend(only_twodays_ago)
    stock['news_content'] = news_content
    return stock


def paraGetNews(data):
    """
    多线程执行爬取
    :param data: generalCacheGet返回的data
    :return: 新的data数据
    """
    new_data = [pool.submit(single_getnews, stock=stock).result() for stock in data]
    return new_data


# ----------------------
# urls差值计算


def get_url_delta(newurls, oldurls):
    """
    用旧的url列表来与新获得的url对比，获得最近更新的url用于爬取，如果两个url完全不同，则返回新的
    :param newurls: 来自爬虫的新cache_urls
    :param oldurls: 从数据库读取的cache_urls
    :return: 一个包含最近更新的cache_urls列表
    """
    delta = list(set(newurls)-set(oldurls))
    delta.sort(key=newurls.index)
    return delta


def paraCacheDiff(ndata):
    """
    通过对数据库中查找的每只股票的cache_urls与爬取的cache_urls进行对比，获取更新的url并爬取新闻
    :param ndata: 经过generalCacheGet修改的qdata
    :return: ndata
    """
    for stock in ndata:
        delta = pool.submit(get_url_delta, newurls=stock['cache'], oldurls=stock['cache_urls']).result()
        stock['cache_delta'] = delta
    return ndata


# -----------------------
# 多线程url过滤


def paraFilter(adddelta):
    """
    对adddelta中的cache_delta进行过滤，用于爬取新闻
    :param adddelta: 来自paraCacheDiff处理过的ndata
    :return: ndata
    """
    for stock in adddelta:
        stock['ready_for_news'] = generalFilter(stock['cache_delta'], '_9_1', 'delete')
    return adddelta

