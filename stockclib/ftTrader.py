# -*- coding: utf-8 -*-
# @Time    : 2017/11/18 17:29
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : ftTrader.py
# @Software: PyCharm
# 本库为富途牛牛模拟交易的API，仅支持headless firefox

from selenium import webdriver
from time import sleep
import re


A_exchange_patterns = [re.compile('[3][0]\d{4}'), re.compile('[0][0]\d{4}'), re.compile('[6][0]\d{4}')]
A_exchange_labels = ['sz', 'sz', 'sh']
A_trade_address = "https://www.futunn.com/trade/cn-trade#%s/%s"
A_cancel_xpath = "//*[@id='orders']/tr[%s]/td[9]/div[1]/a[2]"


def launch_headless(geckopath, timeout):
    """
    负责启动headless firefox
    :param geckopath: 仅限绝对路径
    :param timeout: 仅限数字
    :return: browser对象
    """
    options = webdriver.firefox.options.Options()
    options.add_argument("-headless")
    browser = webdriver.Firefox(executable_path=geckopath, firefox_options=options)
    browser.implicitly_wait(timeout)
    return browser


def debug_gui():
    """
    debug模式，使用GUI firefox
    :return:
    """
    d = webdriver.Firefox()
    d.implicitly_wait(5)
    return d


def ftnn_login(browser, username, passwd):
    """
    实现富途牛牛的登录
    :param browser: browser对象
    :param username: 用户名（仅支持手机号）
    :param passwd: 密码
    :return: browser对象
    """
    login_address = "https://www.futunn.com/trade"
    # fill form
    browser.get(login_address)
    browser.find_element_by_name("email").send_keys(username)
    browser.find_element_by_name("password").send_keys(passwd)
    # login
    browser.find_element_by_class_name("ui-form-submit").click()


def buy_or_sell(browser, ops):
    """
    提供一个通用方法进行买卖的点击
    :param browser: browser对象
    :param ops: 买还是卖
    :return:
    """
    if ops == 'offer':
        # sell
        browser.find_element_by_class_name("btn02").click()
        # confirm
        browser.find_element_by_xpath("//*[@id='confirmDialog']/div[3]/span[2]/button[1]").click()
        # final confirm
        browser.find_element_by_xpath("/html/body/div[12]/div[3]/button").click()
    if ops == 'bid':
        # buy
        browser.find_element_by_class_name("btn01").click()
        # confirm
        browser.find_element_by_xpath("//*[@id='confirmDialog']/div[3]/span[2]/button[1]").click()
        # final confirm
        browser.find_element_by_xpath("/html/body/div[12]/div[3]/button").click()
    if ops != 'offer' and ops != 'bid':
        raise Exception('Wrong ops')


class FtnnTrader(object):
    """
    本Trader类为无状态的交易对象，只负责下单撤单逻辑，不负责验证交易成功与否等工作
    """
    def __init__(self, account, pwd, geckopath, timeout=5, debug=False):
        """
        初始化交易者
        :param account: 用户手机号
        :param pwd: 密码
        :param geckopath: headless模式下需要填写准确的geckodriver路径
        :param timeout: selenium的延时
        :param debug: 是否开启debug，默认关闭，否则启动GUI FF
        """
        self.__account = account
        self.__pwd = pwd
        self.__geckopath = geckopath
        self.__timeout = timeout
        self.__login = False
        if debug:
            self.__browser = debug_gui()
        else:
            self.__browser = launch_headless(self.__geckopath, self.__timeout)

    def check_details(self):
        """
        返回基本信息
        :return: 包含基本信息的字典
        """
        return {'account': self.__account, 'geckopath': self.__geckopath, 'login': self.__login}

    def login(self):
        ftnn_login(self.__browser, self.__account, self.__pwd)
        self.__login = True
        return self.check_details()

    def zbid(self, code, price, amount):
        """
        A股的买函数
        :param code: 股票代码
        :param price: 价格（需要小数点后两位）
        :param amount: 数量（大于等于100且为100的整数倍）
        :return:
        """
        # recognize the exchange
        position = [A_exchange_patterns.index(pattern) for pattern in A_exchange_patterns if pattern.match(code)]
        exchange_code = A_exchange_labels[position[0]]  # 交易所缩写

        # buy
        self.__browser.get(A_trade_address % (exchange_code, code))  # fetch exchange address

        sleep(0.2)
        pricescope = self.__browser.find_element_by_name("price")
        pricescope.clear()
        pricescope.send_keys(price)

        amountscope = self.__browser.find_element_by_name("qty_str")
        amountscope.clear()
        amountscope.send_keys(amount)

        buy_or_sell(self.__browser, ops='bid')

    def zoffer(self, code, price, amount):
        """
        A股的卖函数
        :param code: 股票代码
        :param price: 价格
        :param amount: 数量（小于等于账户上数量且为100的整数倍）
        :return:
        """
        # recognize the exchange
        position = [A_exchange_patterns.index(pattern) for pattern in A_exchange_patterns if pattern.match(code)]
        exchange_code = A_exchange_labels[position[0]]

        # sell
        self.__browser.get(A_trade_address % (exchange_code, code))

        sleep(0.2)
        pricescope = self.__browser.find_element_by_name("price")
        pricescope.clear()
        pricescope.send_keys(price)

        amountscope = self.__browser.find_element_by_name("qty_str")
        amountscope.clear()
        amountscope.send_keys(amount)

        buy_or_sell(self.__browser, ops='offer')

    def zcancel(self, order_post):
        """
        指定位置的单的撤销
        :param order_post: 在网页上排列的顺序，和堆栈一样
        :return:
        """
        # select remaining orders
        self.__browser.find_element_by_xpath("//*[@id='orderSwitch']/div[1]/label[3]/input").click()

        # choose order to cancel
        self.__browser.find_element_by_xpath("//*[@id='orders']/tr[%s]/td[9]/div[1]/a[2]" % order_post).click()

        # confirm cancellation
        self.__browser.find_element_by_xpath("/html/body/div[4]/div[3]/span[2]/button[1]").click()

    def zcancel_all(self):
        """
        一键撤全部单
        :return:
        """
        # select remaining orders
        self.__browser.find_element_by_xpath("//*[@id='orderSwitch']/div[1]/label[3]/input").click()

        # cancel
        self.__browser.find_element_by_xpath("//*[@id='orderSwitch']/div[2]/a").click()

        # confirm cancellation
        self.__browser.find_element_by_xpath("/html/body/div[12]/div[3]/button[1]").click()

    def halt(self):
        """
        关闭浏览器
        :return:
        """
        self.__browser.quit()
        return {'message': 'Webdriver halt'}



















