StockClib 0.3.1
=========
Project Sora depends on this library. Include these modules:  
- dtSearch
- dtLib
- ftTrader
- omServ

## Change log
- 0.3.1:  
修复了一堆恶性bug

- 0.3:   
Add omServ for order matching server  
Disable parallel jieba

## Platform and dependency
- Platform:  
Support Windows and Linux  
Python 3.x

- Python dependency:  
neo4j-driver  
bs4  
jieba  
retrying  
requests  
lxml  
selenium  

- Others
Lastest Firefox(headless mode support)  
Geckodriver 

## Installation
1. Clone the repository and run setup.py

```
git clone https://github.com/Hochikong/SoraComm.git && cd SoraComm
python3 setup.py install
```
Well,if you meet such a error message:  
```
ERROR: b'/bin/sh: 1: xslt-config: not found\n'
** make sure the development packages of libxml2 and libxslt are installed **

Using build configuration of libxslt 
warning: no files found matching '*.html' under directory 'doc'
In file included from src/lxml/etree.c:619:0:
src/lxml/includes/etree_defs.h:14:31: fatal error: libxml/xmlversion.h: No such file or directory
compilation terminated.
Compile failed: command 'x86_64-linux-gnu-gcc' failed with exit status 1
/tmp/easy_install-hww2r01n/lxml-4.1.1/temp/xmlXPathInit4rsgpj61.c:1:26: fatal error: libxml/xpath.h: No such file or directory
compilation terminated.
*********************************************************************************
Could not find function xmlCheckVersion in library libxml2. Is libxml2 installed?
*********************************************************************************
error: Setup script exited with error: command 'x86_64-linux-gnu-gcc' failed with exit status 1
```
You just need to execute this command:

```
apt-get install python3-lxml
```
Then you run the setup.py again and done.

2. Download the geckodriver and install firefox

```
wget https://github.com/mozilla/geckodriver/releases/download/v0.19.1/geckodriver-v0.19.1-linux64.tar.gz
tar xvf geckodriver-v0.19.1-linux64.tar.gz
```
Once you uncompress the tar.gz file, you will see a geckodriver in your current directory. Just move it to a proper place such as /usr/local/bin. 

Then finish Firefox's installation (I assume that you are using Ubuntu or Debian) 
```
apt-get update
apt-get install firefox -y
```

## Usage
I only show the use case of ftTrader to you below

### 1.Create a stock exchange account(simulation)
Visit 富途证券's website and sign up with your phone number: 
[Here](https://passport.futu5.com/?target=https%3A%2F%2Fwww.futunn.com%2F#reg)

Then you can use your phone number and your password to login your trade account.  

### 2.Using python console try ftTrader
```
>>> from stockclib.ftTrader import *
>>> t = FtnnTrader(YOUR_PHONE_NUMBER,YOUR_PASSWD,GECKODRIVER_PATH,TIMEOUT,DEBUG)
>>> t.login()
{'geckopath': '/root/gecko/geckodriver', 'login': True, 'account': 'xxx'}
>>> t.zbid('000858','75.00','200')
```

Let me explain what I did the example above:

1. Import FtnnTrader() and others  

2. Create a trader substance with your user name(your phone number) and your password.  

3. If you want to run it with debug mode, you can use an empty string as geckodriver path then set debug=True, then Firefox will run with GUI.If you want to run it on server, you should run FF with headless mode by declaring the legal geckodriver path and ignore the debug parameter.

4. Once you initial the trader substance, then login()

5. Create an bid order. I want to buy the stock 000858(五粮液) at 75￥, 2 100-Share board lot.

6. Let's check my account:

![](http://oy30yrqej.bkt.clouddn.com/ftnn)

You can also use zoffer create offer order:
```
>>>  t.zoffer('000725','6.2','100')
```

If you want to cancel the orders which still waiting for exchange, you can use zcancel() to cancel a specify order:
```
>>> t.zcancel(1)
```
Due to the website, the latest offer order's position is 1, hence my bid order's position is 2, just like stack(speak frankly,totally not like, because you can select position).  

Briefly, the latest order's position is always 1.

But sometimes you may want a 'one click cancellation', then you can use zcancel_all(): 

```
>>> t.zcancel_all()
```

Finally, you can use halt() to stop the FF:
```
>>> t.halt()
```

### 3.Warning
1. ftTrader is a stateless and no assurance library. I mean you need to store all exchange info by yourselves.You should use legal price, amount. After create orders, you should check the orders' status by yourself. You need to maintain a dict or list in order to cancel your orders.
2. Only support stock which the code start with 30, 00, 60,such as 000725,600001 and 300091.(仅支持A股沪深主板、中小板和创业板)