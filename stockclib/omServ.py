# -*- coding: utf-8 -*-
# @Time    : 2017/12/8 22:50
# @Author  : Hochikong
# @Email   : hochikong@foxmail.com
# @File    : omServ.py
# @Software: PyCharm

from flask import json
import uuid
import random
import string
import time
import pymongo
import tushare
import datetime


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
            ordertotal = round(int(order['amount']) * float(jdict['price']), 2)
            ordertax = 0.0  # 输入的税率和手续费率默认为float型,使用round截断小数
            orderfee = round(ordertotal*feeR, 2)
            if orderfee < 5:
                orderfee = 5
            if ordertotal+ordertax+orderfee > float(authinfo['balance']):  # balance在traders表上为字符串
                return {'status': 'Error', 'msg': "You don't have enough money"}
            else:
                order['price'] = jdict['price']
                order['total'] = str(ordertotal)
                order['tax'] = ordertax   # 买入不收税
                order['fee'] = str(orderfee)
                order['cost'] = str(round(ordertax+orderfee, 2))
                order['order_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                order['user_id'] = authinfo['user_id']
                order['ops'] = jdict['ops']
                order['order_id'] = generate_random_str(10)  # 根据ID才能撤单
                return order

        elif jdict['ops'] == 'offer':
            positions = positions['position']
            position_codes = [p['code'] for p in positions]
            if order['code'] in position_codes:
                ordertotal = round(int(order['amount']) * float(jdict['price']), 2)
                ordertax = round(ordertotal * taxR, 2)
                orderfee = round(ordertotal * feeR, 2)

                if orderfee < 5:
                    orderfee = 5
                order['price'] = jdict['price']
                order['total'] = str(ordertotal)
                order['tax'] = str(ordertax)
                order['fee'] = str(orderfee)
                order['cost'] = str(round(ordertax+orderfee, 2))
                order['order_time'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                order['user_id'] = authinfo['user_id']
                order['ops'] = jdict['ops']
                order['order_id'] = generate_random_str(10)

                return order
            else:
                return {'status': 'Error', 'msg': 'No such position'}
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
    order_data.pop('_id')
    order_data['tprice'] = str(0.0)
    order_data['status'] = 'cancel'
    order_data['done_time'] = time.strftime("%Y-%m-%d", time.localtime())
    return order_data


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


def return_for_tran_history(user_id, per_order, data):
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
                                             'amount': per_order['amount'],
                                             'total': per_order['total'],
                                             'avgprice': data['avgprice'],
                                             'cost': data['cost'], }, ]}


def balance_manager(traders, per_order):
    """
    用于调整用户余额
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
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]  # 指定的数据库
    coll_signal = db[service_signal]  # 使用该文档来识别信号
    return coll_signal


def fetch_others(address, port, username, passwd, target_db, orders, full_history, positions, trans_history, traders):
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]  # 指定的数据库
    cursors = {'coll_orders': db[orders],
               'coll_full_history': db[full_history],
               'coll_positions': db[positions],
               'coll_trans_history': db[trans_history],
               'coll_traders': db[traders]}
    return cursors


def fetch_profitstat(address, port, username, passwd, target_db, traders, positions, profitstat):
    c = mongo_auth_assistant(address, port, username, passwd, target_db)
    db = c[target_db]
    cursors = {'coll_traders': db[traders],
               'coll_positions': db[positions],
               'coll_profitstat': db[profitstat]}
    return cursors


def compare_when_matching(per_order):  # 尚未支持融券
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


def position_manager(per_order, positions):
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
                return return_for_tran_history(user_id, per_order, data)
            else:
                # 非增持的情况
                user_position.append(data)
                # 更新用户持仓
                positions.update_one({'user_id': user_id}, {'$set': {'position': user_position}})
                return return_for_tran_history(user_id, per_order, data)
        else:
            document = {'user_id': user_id, 'position': [data, ]}
            positions.insert_one(document)
            # 用于写入trans_history
            return return_for_tran_history(user_id, per_order, data)
    if per_order['ops'] == 'offer':
        query_result = positions.find_one({'user_id': user_id})
        # 此处不再执行用户是否存在的查询，交给REST接口处理
        position_data = query_result['position']
        # 清除指定记录
        d_index = [position_data.index(d) for d in position_data if d['code'] == per_order['code']][0]
        position_data.pop(d_index)
        # 重新写入数据库
        positions.update_one({'user_id': user_id}, {'$set': {'position': position_data}})
        # 更新trans_history
        return {'end': time.strftime("%Y-%m-%d", time.localtime()),
                'code': per_order['code'],
                'user_id': user_id,
                'current_price': tushare.get_realtime_quotes(per_order['code'])['price'][0]}


def transhistory_manager(trans_history, pm_return):
    # 结算更新
    # 卖出结算
    if len(pm_return) == 4:
        user_id = pm_return['user_id']
        code = pm_return['code']
        query_result = trans_history.find_one({'user_id': user_id})
        history = query_result['history']
        # 买入时写入的不含end的数据
        data = [d for d in history if 'end' not in list(d.keys()) and code in list(d.values())][0]
        data_index = history.index(data)
        # 计算损益
        the_return = round((float(pm_return['current_price'])-float(data['avgprice']))*int(data['amount'])
                           -float(data['cost']), 2)
        return_rate = round((the_return/float(data['total'])), 2)
        # 计算日期
        str_now_1 = pm_return['end'].split('-')
        str_ago_2 = data['start'].split('-')
        str_to_int_now = [int(ele) for ele in str_now_1]
        str_to_int_ago = [int(ele) for ele in str_ago_2]
        now = datetime(str_to_int_now[0], str_to_int_now[1], str_to_int_now[2])
        ago = datetime(str_to_int_ago[0], str_to_int_ago[1], str_to_int_ago[2])
        delta = (now-ago).days
        # 补充数据
        data['end'] = pm_return['end']
        data['the_return'] = str(the_return)
        data['rateofR'] = str(return_rate)
        data['during'] = str(delta)
        history[data_index] = data
        # 写入数据库
        trans_history.update_one({'user_id': user_id}, {'$set': {'history': history}})
    # 买入结算
    if len(pm_return) == 2:
        user_id = pm_return['user_id']
        query_result = trans_history.find_one({'user_id': user_id})
        # 如果用户已存在
        if query_result:
            history = query_result['history']
            history.append(pm_return['history'][0])
            trans_history.update_one({'user_id': user_id}, {'$set': {'history': history}})
        else:
            trans_history.insert_one(pm_return)