# -*- coding: utf-8 -*-
# @Time    : 2017/12/8 22:50
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : omServ.py
# @Software: PyCharm

from flask import json
from functools import reduce
from retrying import retry
import uuid
import random
import logging
import string
import time
import pymongo
import tushare


def generate_random_str(length):
    """
    生成一个固定长度的随机字符串
    :param length: 数字长度
    :return: 随机字符串
    """
    rstr = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))
    return rstr


def modify_print(rawdata):
    """
    根据数据库的查询调整输出，主要是调整balance的项
    :param rawdata: 数据库查询的list后的结果
    :return:
    """
    strdata = []
    try:
        maxbalancelength = len(max([r['balance'] for r in rawdata], key=len))
        maxtotallength = len(max([r['total'] for r in rawdata], key=len))
        useforprint = max(maxbalancelength, maxtotallength)
        for row in rawdata:
            strdata.append('| User ID: %s | Token: %s | Total: %s | Balance: %s |'
                           % (row['user_id'],
                              row['token'],
                              row['total']+' '*(useforprint-len(row['total'])),
                              row['balance']+' '*(useforprint-len(row['balance']))))
        maxlength = len(max(strdata, key=len))
    except ValueError:
        print('No more user now')
    else:
        for row in strdata:
            print('-' * maxlength)
            print(row)
            print('-' * maxlength)


def generate_and_write(raw_param, trader_doc):
    """
    生成用户ID和token并记录total和balance
    :param raw_param: 原始终端输入
    :param trader_doc: 制定的数据库文档
    :return:
    """
    total = raw_param.split("-m ")[-1]
    userid = str(uuid.uuid1())
    usertoken = generate_random_str(50)
    trader_doc.insert_one({'user_id': userid, 'token': usertoken, 'total': total, 'balance': total})
    print('User ID: ', userid, '\n')
    print('Token: ', usertoken)


def helper_print():
    """
    打印帮助
    :return:
    """
    print('gen: 生成新用户并返回信息')
    print(' -m  指定账户可用资金量', '\n')
    print('check: 查询用户信息')
    print(' -a  查询所有用户信息', '\n')
    print('signal: 修改撮合服务信号决定是否进行撮合')
    print(' -r  运行')
    print(' -h  停止', '\n')
    print('exit: 退出工具', '\n')
    print('目前所有可用参数均强制使用')


def json_to_dict(rawdata):
    """
    把request中的json转换为字典
    :param rawdata: request.data
    :return: python dict
    """
    jsonstr = rawdata
    jsondict = json.loads(jsonstr, encoding='utf-8')
    return jsondict


def token_certify(document, header):
    """
    根据传入的headers找到trade_token值并在数据库中查找对应的ID，若存在则返回用户数据，否则返回错误信息
    :param document: traders文档
    :param header: request.headers
    :return: python dict
    """
    query = [x for x in list(document.find()) if header['trade_token'] in list(x.values())]
    if len(query) > 0:
        return query[0]
    else:
        return {'status': 'Error', 'msg': 'No such user'}


def check_orders(jdict, authinfo, taxR, feeR, positions):
    """
    从原始json转化的dict中获取指定的值，防止输入不允许的内容，不设10%涨跌幅
    :param jdict: 交易请求中的jdict
    :param authinfo: authentication information
    :param taxR: 印花税率，int类型
    :param feeR: 手续费率，int类型，不足5元算5元
    :param positions: 指定用户的持仓数据文档
    :return: python dict
    """
    try:
        order = {'code': jdict['code'], 'name': jdict['name']}

        # 检查数量是否合规
        if int(jdict['amount']) % 100 == 0:
            order['amount'] = jdict['amount']
        else:
            return {'status': 'Error', 'msg': 'Amount should be multiple of 100'}

        # 费用验证(仅验证能不能交易)
        if jdict['ops'] == 'bid':
            ordertotal = round(int(order['amount']) * float(jdict['price']), 2)  # total不含费用，只是总额的意思
            ordertax = 0.0  # 输入的税率和手续费率默认为float型,使用round截断小数
            orderfee = round(ordertotal*feeR, 2)
            if orderfee < 5:
                orderfee = 5
            if ordertotal+ordertax+orderfee > float(authinfo['balance']):  # balance在traders表上为字符串
                return {'status': 'Error', 'msg': "You don't have enough money"}
            else:
                order['price'] = jdict['price']
                order['total'] = str(ordertotal)
                order['tax'] = str(ordertax)   # 买入不收税
                order['fee'] = str(orderfee)
                order['cost'] = str(round(ordertax+orderfee, 2))
                order['order_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                order['user_id'] = authinfo['user_id']
                order['ops'] = jdict['ops']
                order['order_id'] = generate_random_str(10)  # 根据ID才能撤单
                return order

        elif jdict['ops'] == 'offer':
            if positions:  # 防止空仓卖出的bug
                positions = positions['position']
                position_codes = [p['code'] for p in positions]
                if order['code'] in position_codes:
                    amount_to_code = [int(p['amount']) for p in positions if order['code'] in list(p.values())][0]
                    if amount_to_code < int(order['amount']):  # 检查股票数量够不够卖
                        return {'status': 'Error', 'msg': "You don't have enough amount to sell"}
                    else:
                        ordertotal = round(int(order['amount']) * float(jdict['price']), 2)
                        ordertax = round(ordertotal * taxR, 2)
                        orderfee = round(ordertotal * feeR, 2)

                        if orderfee < 5:
                            orderfee = 5
                        order['price'] = jdict['price']
                        order['total'] = str(ordertotal)
                        order['tax'] = str(ordertax)
                        order['fee'] = str(orderfee)
                        order['cost'] = str(round(ordertax + orderfee, 2))
                        order['order_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        order['user_id'] = authinfo['user_id']
                        order['ops'] = jdict['ops']
                        order['order_id'] = generate_random_str(10)
                        return order
                else:
                    return {'status': 'Error', 'msg': 'No such position'}
            else:
                return {'status': 'Error', 'msg': 'No such position now'}
        else:
            return {'status': 'Error', 'msg': "Wrong ops"}

    except KeyError:
        return {'status': 'Error', 'msg': "Invalid input or wrong requests body"}


def mongo_auth_assistant(address, port, username, passwd, database):
    """
    用于简化MongoDB认证
    :param address: ...
    :param port: ...
    :param username: ...
    :param passwd: ...
    :param database: 用户所属数据库
    :return: 连接对象
    """
    connection = pymongo.MongoClient(address, port)
    if connection.admin.authenticate(username, passwd, mechanism='SCRAM-SHA-1', source=database):
        pass
    else:
        raise Exception('Error configure on user or password! ')
    return connection


def clean_order(order_data):
    """
    对订单数据进行处理，方便写入full_history
    :param order_data: 来自原始订单数据的数据
    :return:
    """
    if order_data:
        order_data.pop('_id')
        order_data['tprice'] = str(0.0)
        order_data['status'] = 'cancel'
        order_data['done_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        return order_data
    else:
        pass


def clean_order_for_om(per_order, price):
    """
    为OMSERVER提供的订单数据清理函数，作用类似clean_order
    :param per_order: per_order的数据
    :param price: compare_result
    :return:
    """
    per_order.pop('_id')
    per_order['status'] = 'done'
    per_order['done_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    per_order['tprice'] = price
    return per_order


def cost_cal_for_om(per_order, feeR, taxR):
    """
    根据实际价格重新计算total、cost、tax和fee
    :param per_order: per_order数据
    :param feeR: 手续费率
    :param taxR: 税率
    :return:
    """
    nprice = float(per_order['tprice'])
    namount = int(per_order['amount'])
    nfee = round(nprice*namount*feeR, 2)
    if nfee < 5:  # 手续费不够5元算够5元
        nfee = 5
    ntotal = round(nprice*namount, 2)
    if per_order['ops'] == 'bid':
        ntax = 0.0
    elif per_order['ops'] == 'offer':  # 卖出收税
        ntax = round(nprice*namount*taxR, 2)
    ncost = nfee+ntax
    # 更新数据
    per_order['total'] = str(ntotal)
    per_order['cost'] = str(ncost)
    per_order['tax'] = str(ntax)
    per_order['fee'] = str(nfee)
    return per_order


def avgprice_update(avgp_multi_amount, sell_total_plus_cost, remain_amount):
    """
    用于卖出部分股票时更新现价
    :param avgp_multi_amount: 持仓中的均价*数量
    :param sell_total_plus_cost: 卖出总额+成本
    :param remain_amount: 余下的股票数量
    :return: 最新均价
    """
    result = (avgp_multi_amount - sell_total_plus_cost) / remain_amount
    return result


def generate_positions(per_order):
    """
    在写入positions表前生成数据
    :param per_order: per_order数据
    :return:
    """
    data = {'code': per_order['code'],
            'name': per_order['name'],
            'amount': per_order['amount'],
            'total': per_order['total'],
            'avgprice': str(
                round((float(per_order['total']) + float(per_order['cost'])) / float(per_order['amount']), 2)),
            'cost': per_order['cost']
            }
    return data


def generate_positions_update(code_index, per_order, user_position):
    """
    在增持股票的情况下计算cost、total等更新值
    :param code_index: 被增持股票数据的位置
    :param per_order: per_order数据
    :param user_position: 用户现有持仓数据
    :return:
    """
    n_amount = int(per_order['amount']) + int(user_position[code_index]['amount'])
    n_total = float(per_order['total']) + float(user_position[code_index]['total'])
    n_cost = float(per_order['cost']) + float(user_position[code_index]['cost'])
    n_avgprice = round(((n_total + n_cost) / n_amount), 2)
    data_update = {'amount': str(n_amount),
                   'total': str(n_total),
                   'avgprice': str(n_avgprice),
                   'cost': str(n_cost)
                   }
    return data_update


def return_for_trans_history(user_id, per_order, data):
    """
    返回合适的数据供写入trans_history表
    :param user_id: 用户id
    :param per_order: per_order数据
    :param data: 仓位数据
    :return:
    """
    return {'user_id': user_id, 'history': [{'start': time.strftime("%Y-%m-%d", time.localtime()),
                                             'code': per_order['code'],
                                             'name': per_order['name'],
                                             }, ]}


def balance_manager(traders, per_order):
    """
    获取来自position_manager的数据，用于调整用户余额
    :param traders: traders表
    :param per_order: per_order数据
    :return:
    """
    user_id = per_order['user_id']
    if per_order['ops'] == 'bid':
        delta = float(per_order['total']) + float(per_order['cost'])
        query = traders.find_one({'user_id': user_id})
        balance = query['balance']
        new_balance = str(round((float(balance) - delta), 2))
        # 更新余额
        traders.update_one({'user_id': user_id}, {'$set': {'balance': new_balance}})
    if per_order['ops'] == 'offer':
        delta = float(per_order['total']) - float(per_order['cost'])
        query = traders.find_one({'user_id': user_id})
        balance = query['balance']
        new_balance = str(round((float(balance) + delta),2))
        traders.update_one({'user_id': user_id}, {'$set': {'balance': new_balance}})


def fetch_signal(address, port, username, passwd, target_db, service_signal):
    """
    辅助获取omserver的信号集合
    :param address: 地址
    :param port: 端口，int类型
    :param username: 用户名
    :param passwd: 用户密码
    :param target_db: 登陆用的数据库
    :param service_signal: 指定的信号集合名，str类型
    :return:
    """
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]  # 指定的数据库
    coll_signal = db[service_signal]  # 使用该文档来识别信号
    return coll_signal


def fetch_others(address, port, username, passwd, target_db, orders, full_history, positions, trans_history, traders):
    """
    功能和fetch_signal类似
    :param address: 不再复述
    :param port: ~
    :param username: ~
    :param passwd: ~
    :param target_db: ~
    :param orders: 指定的订单集合名，str类型
    :param full_history: 指定的操作历史集合名，str类型
    :param positions: 指定的仓位集合名，str类型
    :param trans_history: 指定的交易历史集合名，str类型
    :param traders: 指定的用户集合名，str类型
    :return:
    """
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]  # 指定的数据库
    cursors = {'coll_orders': db[orders],
               'coll_full_history': db[full_history],
               'coll_positions': db[positions],
               'coll_trans_history': db[trans_history],
               'coll_traders': db[traders]}
    return cursors


def fetch_profitstat(address, port, username, passwd, target_db, traders, positions, profitstat):
    """
    功能与其他的fetch函数类似，参数不再复述
    :param address:
    :param port:
    :param username:
    :param passwd:
    :param target_db:
    :param traders:
    :param positions:
    :param profitstat:
    :return:
    """
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]
    cursors = {'coll_traders': db[traders],
               'coll_positions': db[positions],
               'coll_profitstat': db[profitstat]}
    return cursors


@retry(stop_max_attempt_number=5)
def compare_when_matching(per_order):  # 尚未支持融券
    """
    针对订单数据中的方向和价格，判定是否能成交，买单若高于现价则按现价成交，卖单若低于现价也按现价成交
    :param per_order: 订单数据
    :return: Wait或价格的字符串
    """
    code = per_order['code']
    price = float(per_order['price'])
    ops = per_order['ops']
    current_price = float(tushare.get_realtime_quotes(code)['price'][0])
    # 买入撮合
    if ops == 'bid':
        if price >= current_price:
            return str(current_price)
        else:
            return 'Wait'
    # 卖出撮合
    if ops == 'offer':
        if price <= current_price:
            return str(current_price)
        else:
            return 'Wait'


def matching_without_waiting(per_order):
    """
    忽略价格直接成交
    :param per_order: 订单数据
    :return: 价格字符串
    """
    price = float(per_order['price'])
    return str(price)


def real_time_profit_statistics(traders, positions):
    """
    提供实时总收益率和单股票的盈亏和盈亏率
    :param traders: 用户集合
    :param positions: 仓位集合
    :return: 返回一个含全部用户实时损益的数据
    """
    stats = []
    # 持仓用户的计算方法：持仓股票现市值之和加余额除本金
    all_users = list(traders.find())
    all_positions = list(positions.find())

    # 无持仓用户计算方法： 余额与本金差值除本金
    all_user_with_positions = [p['user_id'] for p in all_positions if len(p['position']) > 0]  # ['user_id','user_id']
    all_user_without_positions = [u for u in all_users if u['user_id'] not in all_user_with_positions]
    for u in all_user_without_positions:
        u_balance = float(u['balance'])
        u_total = float(u['total'])
        u_AllrateR = round((u_balance-u_total)/u_total, 3)
        stats.append({'user_id': u['user_id'], 'stat': [{
            'date': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            'balance': str(u_balance),
            'AllrateR': str(u_AllrateR)}]})

    # 计算持仓用户的收益
    # 提取余额与本金
    all_user_total_balance = []   # [['total', 'balance'], ['total', 'balance']]
    for user_id in all_user_with_positions:
        for info in all_users:
            if user_id in list(info.values()):
                all_user_total_balance.append({'user_id': user_id, 'data': [info['total'], info['balance']]})
    # 提取代码、用户id、均价和数量
    all_code_avgprice_amount = []
    for u in all_positions:
        for p in u['position']:
            data = {'user_id': u['user_id'], 'caa': (p['code'], p['avgprice'], p['amount'])}
            all_code_avgprice_amount.append(data)
    # 更新现价
    for i in all_code_avgprice_amount:
        code = i['caa'][0]  # caa是代码code、成本价avgprice和数量amount
        i['now_price'] = tushare.get_realtime_quotes(code)['price'][0]
    # 计算现市值
    for i in all_code_avgprice_amount:
        now_total = int(i['caa'][2])*float(i['now_price'])
        i['s_now_total'] = round(now_total, 2)
    # 计算单只股票盈亏率与盈亏
    for stock in all_code_avgprice_amount:
        s_origin_total = round(float(stock['caa'][1])*int(stock['caa'][2]), 2)
        delta = stock['s_now_total']-s_origin_total
        stock_rateR = round(delta/s_origin_total, 4)
        stock['return'] = delta
        stock['rateR'] = stock_rateR
    # 加上余额求差值
    for user_id in all_user_with_positions:
        user_id_total = [i['s_now_total'] for i in all_code_avgprice_amount if user_id in list(i.values())]
        user_id_total = reduce(lambda x, y: x + y, user_id_total)
        # 用户股票总市值加上余额
        user_id_now_balance = [float(i['data'][1]) for i in all_user_total_balance if user_id in list(i.values())][0]
        user_id_a_total = user_id_now_balance + user_id_total
        # 本金
        user_id_origin_total = [float(i['data'][0]) for i in all_user_total_balance if user_id in list(i.values())][0]
        # 算收益率
        AllrateR = round((user_id_a_total-user_id_origin_total)/user_id_origin_total, 4)
        stat = {'user_id': user_id, 'stat': [{'date': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                                              'balance': str(user_id_now_balance),
                                              'AllrateR': str(AllrateR)}],
                                    'stocks_rateR': []}

        all_names_with_code = [(u['code'],u['name']) for u in all_positions[0]['position']]
        # 写入单只股票的盈亏
        for s in all_code_avgprice_amount:
            if user_id == s['user_id']:
                datastruct = {'name': [n[1] for n in all_names_with_code if s['caa'][0] in n][0],
                              'code': s['caa'][0],
                              'avgprice': s['caa'][1],
                              'amount': s['caa'][2],
                              'current_price': s['now_price'],
                              'current_total': str(s['s_now_total']),
                              'return': str(s['return']),
                              'rateR': str(s['rateR'])}
                stat['stocks_rateR'].append(datastruct)
        stats.append(stat)
    return stats


def update_signal(oms, signal):
    """
    更新ordermatch_service表的status字段
    :param oms: 数据库ordermatch_service集合
    :param signal: 字符串halt或者run
    :return:
    """
    query = oms.find_one()
    if query:
        query.pop('_id')
        old_status = query['status']
        oms.update_one({'status': old_status}, {'$set': {'status': signal}})
    else:
        data = {'status': signal}
        oms.insert_one(data)


def position_manager(per_order, positions):
    """
    仓位管理函数
    :param per_order: 一张订单
    :param positions: positions集合
    :return:
    """
    user_id = per_order['user_id']
    if per_order['ops'] == 'bid':
        data = generate_positions(per_order)
        # 检查用户是否存在position表中
        query_result = positions.find_one({'user_id': user_id})
        # 如果已存在
        if query_result:
            user_position = query_result['position']
            # 检查是否已经持有该股票
            codes = [p['code'] for p in user_position]
            # 增持
            if per_order['code'] in codes:
                # 计算增持时total等数据的新变化
                code_index = codes.index(per_order['code'])
                data_update = generate_positions_update(code_index, per_order, user_position)
                # 把更新应用到原数据持仓信息里
                for k in list(data_update.keys()):
                    user_position[code_index][k] = data_update[k]
                # 更新数据库
                positions.update_one({'user_id': user_id}, {'$set': {'position': user_position}})
            else:
                # 非增持的情况
                user_position.append(data)
                # 更新用户持仓
                positions.update_one({'user_id': user_id}, {'$set': {'position': user_position}})
        else:
            document = {'user_id': user_id, 'position': [data, ]}
            positions.insert_one(document)
    if per_order['ops'] == 'offer':
        query_result = positions.find_one({'user_id': user_id})
        # 此处不再执行用户是否存在的查询，交给REST接口处理
        position_data = query_result['position']

        d_index = [position_data.index(d) for d in position_data if d['code'] == per_order['code']][0]

        # 减持
        if int(per_order['amount']) < int(position_data[d_index]['amount']):
            origin_position = position_data[d_index]

            # 均价乘剩余数量
            avgp_multi_amount = round(int(origin_position['amount']) * float(origin_position['avgprice']), 3)
            # 卖出总额加费用
            sell_total_plus_cost = round((int(per_order['amount']) * float(per_order['tprice'])) + float(per_order['cost']), 3)
            # 剩余股票数
            # 更新数量
            origin_position['amount'] = str(int(origin_position['amount']) - int(per_order['amount']))
            remain_amount = origin_position['amount']

            # 更新持仓均价
            newavgprice = round(avgprice_update(avgp_multi_amount, sell_total_plus_cost, int(remain_amount)), 2)
            origin_position['avgprice'] = str(newavgprice)
            # 更新总额
            origin_position['total'] = str(int(remain_amount) * newavgprice)
            # 追加cost(cost字段是不断累加的)
            origin_position['cost'] = str(round(float(origin_position['cost']) + float(per_order['cost']), 2))

            position_data.pop(d_index)
            position_data.append(origin_position)
            positions.update_one({'user_id': user_id}, {'$set': {'position': position_data}})
        # 平仓
        if int(per_order['amount']) == int(position_data[d_index]['amount']):
            position_data.pop(d_index)
            # 重新写入数据库
            positions.update_one({'user_id': user_id}, {'$set': {'position': position_data}})


def generate_logger(name, log_file, level=logging.INFO):
    """
    通用的日志记录模块，用于不同功能的日志记录工作,设置了level之后需要调用相应的方法才能记录日志，
    但level是WARNING的话调用info()就不会留下记录
    :param name: logger名
    :param log_file: 日志文件
    :param level: 日志级别，默认INFO
    :return: logger对象
    """
    formatter = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s')
    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def generate_fhist_csv(token, tds, fhist):
    """
    用于打印操作记录
    :param token: 用户的trade token
    :param tds: traders集合
    :param fhist: full_history集合
    :return:
    """
    query = list(tds.find())
    user_id = [i['user_id'] for i in query if token == i['token']][0]

    full_history = list(fhist.find())

    all_history = []
    for i0 in full_history:
        if i0['user_id'] == user_id:
            all_history.append(i0)

    if len(all_history) > 0:
        keys = list(all_history[0].keys())
        keys.remove('_id')

        bids = []
        offers = []
        for i in all_history:
            if i['status'] == 'done':
                if i['ops'] == 'bid':
                    bids.append(i)
                if i['ops'] == 'offer':
                    offers.append(i)
            else:
                pass

        if len(bids) > 0 and len(offers) > 0:
            # 返回单独的买卖记录和完整操作历史
            for x in bids:
                x.pop('_id')
            for y in offers:
                y.pop('_id')

            head = reduce(lambda x0, y0: x0+','+y0, keys)+'\n'
            body = []
            for dt in all_history:
                tmp = [dt[k0] for k0 in keys]
                body.append(tmp)
            newbody = []
            for l0 in body:
                newbody.append(reduce(lambda x0, y0: x0+','+y0, l0)+'\n')
            # 全部操作历史
            newbody.append(' '*len(head)+'\n')
            # 转成字符串
            newbody = reduce(lambda xn, yn: xn+yn, newbody)

            # 打印单只股票的完整操作
            above_head = 'Full History: '+'\n'
            stocks_ophist = '-'*len(head)+'\n'
            readme = 'Bid and Offer: '+'\n'
            bd0_b = [[i1[k1] for k1 in keys] for i1 in bids]
            bd1_o = [[i1[k2] for k2 in keys] for i1 in offers]
            bid_readme = 'Bid: '+'\n'
            offer_readme = 'Offer: '+'\n'
            bid_body = reduce(lambda xb0, yb0: xb0+yb0, [reduce(lambda x0, y0: x0+','+y0, br)+'\n' for br in bd0_b])
            offer_body = reduce(lambda xo0, yo0: xo0+yo0, [reduce(lambda x0, y0: x0+','+y0, br)+'\n' for br in bd1_o])

            # 构成csv
            elements = [above_head, '\n', head, newbody, readme, '\n', bid_readme, stocks_ophist, bid_body,
                        '\n', offer_readme, stocks_ophist, offer_body, '\n']

            target = reduce(lambda xt, yt: xt+yt, elements)
            yield target
        else:
            # 仅返回全部操作记录
            above_head = 'Full History: ' + '\n'
            head = reduce(lambda x0, y0: x0 + ',' + y0, keys) + '\n'
            body = []
            for dt in all_history:
                tmp = [dt[k0] for k0 in keys]
                body.append(tmp)
            newbody = []
            for l0 in body:
                newbody.append(reduce(lambda x0, y0: x0 + ',' + y0, l0) + '\n')
            newbody = reduce(lambda xn, yn: xn + yn, newbody)

            # 构成csv
            elements = [above_head, '\n', head, newbody]
            target = reduce(lambda xt, yt: xt + yt, elements)
            yield target
    else:
        yield "No History"

