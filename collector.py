#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик средств для сети Base
Собирает токены с нескольких кошельков на один целевой кошелек
"""

import os
import sys
import time
import requests
from web3 import Web3
from config import (
    RPC_URL, ALTERNATIVE_RPC_URLS, RECIPIENT_ADDRESS,
    TOKEN_ADDRESS, GAS_PRICE, GAS_LIMIT, DELAY,
    SCAN_BLOCKS, SCAN_BATCH_DELAY
)

# ERC-20 ABI
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# ERC-721 (NFT) ABI
ERC721_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_index", "type": "uint256"}],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_tokenId", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]

# ERC-1155 (Multi-token NFT) ABI
ERC1155_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_id", "type": "uint256"}
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_id", "type": "uint256"},
            {"name": "_value", "type": "uint256"},
            {"name": "_data", "type": "bytes"}
        ],
        "name": "safeTransferFrom",
        "outputs": [],
        "type": "function"
    }
]

# Basescan API URL
BASESCAN_API_URL = "https://api.basescan.org/api"


class Logger:
    """Класс для логирования"""
    
    def __init__(self, level='info'):
        self.level = level
        self.levels = {'debug': 0, 'info': 1, 'warn': 2, 'error': 3}
    
    def log(self, level, message, data=None):
        if self.levels[level] >= self.levels[self.level]:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            prefix = f"[{timestamp}] [{level.upper()}]"
            
            if data:
                print(f"{prefix} {message}", data)
            else:
                print(f"{prefix} {message}")
    
    def debug(self, message, data=None):
        self.log('debug', message, data)
    
    def info(self, message, data=None):
        self.log('info', message, data)
    
    def warn(self, message, data=None):
        self.log('warn', message, data)
    
    def error(self, message, data=None):
        self.log('error', message, data)


logger = Logger('info')


def load_private_keys():
    """Загружает приватные ключи из .env файла"""
    keys = []
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and not line.startswith('//'):
                        keys.append(line)
            if keys:
                return keys
        except Exception as e:
            logger.error(f"Ошибка при чтении .env файла: {e}")
    
    logger.error("Не найден файл .env с приватными ключами")
    return []


def get_provider():
    """Получает провайдер Web3, пробуя основную и альтернативные RPC"""
    rpc_urls = [RPC_URL] + ALTERNATIVE_RPC_URLS
    
    for rpc_url in rpc_urls:
        try:
            logger.info(f"Попытка подключиться к: {rpc_url}")
            provider = Web3(Web3.HTTPProvider(rpc_url))
            
            # Проверяем подключение
            block_number = provider.eth.block_number
            logger.info(f"Подключено к сети. Последний блок: {block_number}")
            return provider
        except Exception as e:
            logger.warn(f"Не удалось подключиться к {rpc_url}: {e}")
            continue
    
    raise Exception("Не удалось подключиться ни к одной RPC ноде")


def get_token_balance(provider, address, token_address):
    """Получает баланс токена для адреса"""
    try:
        contract = provider.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        balance = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
        decimals = contract.functions.decimals().call()
        return balance, decimals
    except Exception as e:
        logger.error(f"Ошибка при получении баланса токена для {address}: {e}")
        return 0, 18


def get_token_symbol(provider, token_address):
    """Получает символ токена"""
    try:
        contract = provider.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        symbol = contract.functions.symbol().call()
        return symbol
    except:
        return "UNKNOWN"


def get_token_name(provider, token_address):
    """Получает название токена"""
    try:
        contract = provider.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        name = contract.functions.name().call()
        return name
    except:
        return "Unknown Token"


def find_tokens_from_transactions(provider, address, limit_blocks=50000):
    """Находит токены из транзакций кошелька - оптимизированный быстрый метод"""
    found_tokens = set()
    
    try:
        current_block = provider.eth.block_number
        start_block = max(0, current_block - limit_blocks)
        
        logger.info(f"Поиск токенов (последние {limit_blocks} блоков ≈ {limit_blocks * 2 // 60} минут истории)")
        
        transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)")
        checksum_address = Web3.to_checksum_address(address)
        address_padded = '0x' + '0' * 24 + checksum_address[2:].lower()
        
        # Уменьшаем размер батча и добавляем задержки для избежания 503 ошибок
        batch_size = 5000  # Меньший батч для стабильности
        current = start_block
        total_batches = (current_block - start_block) // batch_size + 1
        
        logger.info(f"Сканирование блоков {start_block} - {current_block} ({total_batches} батчей)")
        
        batch_num = 0
        retry_max = 3  # Максимум попыток повтора
        
        while current < current_block:
            batch_end = min(current + batch_size, current_block)
            batch_num += 1
            
            # Повторные попытки при ошибках
            success = False
            for retry in range(retry_max):
                try:
                    # Получаем события где адрес - получатель (входящие транзакции)
                    logs_to = provider.eth.get_logs({
                        'fromBlock': current,
                        'toBlock': batch_end,
                        'topics': [
                            transfer_topic,
                            None,  # any from
                            address_padded  # to address
                        ]
                    })
                    
                    for log in logs_to:
                        if log['address']:
                            found_tokens.add(Web3.to_checksum_address(log['address']))
                    
                    # Получаем события где адрес - отправитель (исходящие транзакции)
                    # Это важно для поиска токенов, которые были отправлены
                    logs_from = provider.eth.get_logs({
                        'fromBlock': current,
                        'toBlock': batch_end,
                        'topics': [
                            transfer_topic,
                            address_padded,  # from address
                            None  # any to
                        ]
                    })
                    
                    for log in logs_from:
                        if log['address']:
                            found_tokens.add(Web3.to_checksum_address(log['address']))
                    
                    total_logs = len(logs_to) + len(logs_from)
                    if total_logs > 0:
                        logger.info(f"  [{batch_num}/{total_batches}] Блоки {current}-{batch_end}: {total_logs} событий ({len(logs_to)} входящих, {len(logs_from)} исходящих) → {len(found_tokens)} токенов")
                    else:
                        logger.debug(f"  [{batch_num}/{total_batches}] Блоки {current}-{batch_end}: событий нет")
                    
                    success = True
                    break  # Успешно, выходим из цикла retry
                    
                except Exception as e:
                    error_msg = str(e)
                    if "503" in error_msg or "Service Unavailable" in error_msg:
                        if retry < retry_max - 1:
                            wait_time = (retry + 1) * 2  # 2, 4, 6 секунд
                            logger.warn(f"  Батч {current}-{batch_end}: Ошибка 503, повтор через {wait_time}с (попытка {retry + 1}/{retry_max})")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"  Батч {current}-{batch_end}: Ошибка 503 после {retry_max} попыток, пропуск")
                    else:
                        logger.warn(f"  Батч {current}-{batch_end}: Ошибка {error_msg}")
                        break  # Для других ошибок не повторяем
            
            # Задержка между батчами для избежания перегрузки RPC
            if current < current_block - 1:  # Не ждем после последнего батча
                time.sleep(SCAN_BATCH_DELAY)
            
            current = batch_end + 1
        
        logger.info(f"✓ Найдено {len(found_tokens)} уникальных токенов")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при поиске токенов: {e}")
        import traceback
        logger.debug(traceback.format_exc())
    
    return list(found_tokens)


def scan_wallet_all_tokens(provider, address):
    """Сканирует кошелек на наличие всех токенов - быстрый оптимизированный метод"""
    tokens_found = []
    
    # Проверяем баланс BASE (нативного токена)
    try:
        base_balance = provider.eth.get_balance(Web3.to_checksum_address(address))
        base_balance_formatted = Web3.from_wei(base_balance, 'ether')
        if base_balance > 0:
            tokens_found.append({
                'address': 'BASE',
                'symbol': 'BASE',
                'name': 'Base Native Token',
                'balance': base_balance,
                'balance_formatted': float(base_balance_formatted),
                'decimals': 18,
                'type': 'NATIVE'
            })
    except Exception as e:
        logger.debug(f"Ошибка при получении баланса BASE: {e}")
    
    # Быстрый метод: ищем токены из транзакций
    # На Base: 1 блок ≈ 2 секунды, 1 день ≈ 43200 блоков
    logger.info(f"Поиск токенов для {address}...")
    token_addresses = find_tokens_from_transactions(provider, address, limit_blocks=SCAN_BLOCKS)
    
    logger.info(f"Проверка балансов для {len(token_addresses)} найденных токенов...")
    
    # Проверяем балансы найденных токенов
    for token_address in token_addresses:
        try:
            # Сначала пробуем как ERC-20
            try:
                balance, decimals = get_token_balance(provider, address, token_address)
                if balance > 0:
                    symbol = get_token_symbol(provider, token_address)
                    name = get_token_name(provider, token_address)
                    
                    tokens_found.append({
                        'address': token_address,
                        'symbol': symbol,
                        'name': name,
                        'balance': balance,
                        'balance_formatted': balance / (10 ** decimals),
                        'decimals': decimals,
                        'type': 'ERC-20'
                    })
                    continue
            except:
                pass
            
            # Если не ERC-20, пробуем как ERC-721 (NFT)
            try:
                contract = provider.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=ERC721_ABI
                )
                balance = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
                
                if balance > 0:
                    try:
                        symbol = contract.functions.symbol().call()
                        name = contract.functions.name().call()
                    except:
                        symbol = "NFT"
                        name = "NFT Collection"
                    
                    tokens_found.append({
                        'address': token_address,
                        'symbol': symbol,
                        'name': name,
                        'balance': balance,
                        'balance_formatted': float(balance),
                        'decimals': 0,
                        'type': 'ERC-721'
                    })
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Ошибка при обработке токена {token_address}: {e}")
            continue
    
    return tokens_found


def scan_all_wallets(provider, accounts):
    """Сканирует все кошельки и собирает информацию о токенах через события Transfer"""
    all_tokens = {}  # token_address -> {symbol, name, type, total_balance, wallets}
    
    logger.info('=== СКАНИРОВАНИЕ КОШЕЛЬКОВ ===\n')
    logger.info('Поиск всех токенов через события Transfer в блокчейне\n')
    
    for i, account in enumerate(accounts):
        address = account.address
        logger.info(f'Сканирование кошелька {i + 1}/{len(accounts)}: {address}')
        
        # Сканируем все токены на кошельке
        tokens = scan_wallet_all_tokens(provider, address)
        
        # Добавляем информацию о найденных токенах
        for token in tokens:
            token_address = token['address']
            if token_address not in all_tokens:
                all_tokens[token_address] = {
                    'symbol': token['symbol'],
                    'name': token.get('name', 'Unknown'),
                    'type': token.get('type', 'ERC-20'),
                    'decimals': token.get('decimals', 18),
                    'total_balance': 0,
                    'wallets': []
                }
            
            all_tokens[token_address]['total_balance'] += token['balance_formatted']
            all_tokens[token_address]['wallets'].append({
                'address': address,
                'balance': token['balance_formatted']
            })
        
        logger.info(f'   Найдено токенов: {len(tokens)}')
    
    return all_tokens


def display_available_tokens(all_tokens):
    """Отображает список всех найденных токенов"""
    logger.info('\n=== НАЙДЕННЫЕ ТОКЕНЫ И NFT ===\n')
    
    if not all_tokens:
        logger.warn('Токены не найдены на кошельках')
        return []
    
    token_list = []
    index = 1
    
    # Группируем по типам
    native_tokens = []
    erc20_tokens = []
    nft_tokens = []
    
    for token_address, token_info in all_tokens.items():
        token_type = token_info.get('type', 'ERC-20')
        if token_type == 'NATIVE':
            native_tokens.append((token_address, token_info))
        elif token_type == 'ERC-721':
            nft_tokens.append((token_address, token_info))
        else:
            erc20_tokens.append((token_address, token_info))
    
    # Выводим нативные токены
    if native_tokens:
        logger.info('--- Нативные токены ---')
        for token_address, token_info in native_tokens:
            logger.info(f"{index}. [{token_info['type']}] {token_info['symbol']} - {token_info.get('name', '')}")
            logger.info(f"   Адрес: {token_address}")
            logger.info(f"   Общий баланс: {token_info['total_balance']:.6f}")
            logger.info(f"   Найдено на {len(token_info['wallets'])} кошельке(ах):")
            for wallet_info in token_info['wallets']:
                logger.info(f"      - {wallet_info['address']}: {wallet_info['balance']:.6f}")
            logger.info('')
            token_list.append({
                'index': index,
                'address': token_address,
                'symbol': token_info['symbol'],
                'name': token_info.get('name', ''),
                'type': token_info['type'],
                'total_balance': token_info['total_balance']
            })
            index += 1
    
    # Выводим ERC-20 токены
    if erc20_tokens:
        logger.info('--- ERC-20 Токены ---')
        for token_address, token_info in erc20_tokens:
            logger.info(f"{index}. [{token_info['type']}] {token_info['symbol']} - {token_info.get('name', '')}")
            logger.info(f"   Адрес: {token_address}")
            logger.info(f"   Общий баланс: {token_info['total_balance']:.6f}")
            logger.info(f"   Найдено на {len(token_info['wallets'])} кошельке(ах):")
            for wallet_info in token_info['wallets']:
                logger.info(f"      - {wallet_info['address']}: {wallet_info['balance']:.6f}")
            logger.info('')
            token_list.append({
                'index': index,
                'address': token_address,
                'symbol': token_info['symbol'],
                'name': token_info.get('name', ''),
                'type': token_info['type'],
                'total_balance': token_info['total_balance']
            })
            index += 1
    
    # Выводим NFT
    if nft_tokens:
        logger.info('--- NFT (ERC-721) ---')
        for token_address, token_info in nft_tokens:
            logger.info(f"{index}. [{token_info['type']}] {token_info['symbol']} - {token_info.get('name', 'NFT Collection')}")
            logger.info(f"   Адрес: {token_address}")
            logger.info(f"   Всего NFT: {int(token_info['total_balance'])}")
            logger.info(f"   Найдено на {len(token_info['wallets'])} кошельке(ах):")
            for wallet_info in token_info['wallets']:
                logger.info(f"      - {wallet_info['address']}: {int(wallet_info['balance'])} NFT")
            logger.info('')
            token_list.append({
                'index': index,
                'address': token_address,
                'symbol': token_info['symbol'],
                'name': token_info.get('name', 'NFT Collection'),
                'type': token_info['type'],
                'total_balance': token_info['total_balance']
            })
            index += 1
    
    return token_list


def select_token(token_list):
    """Позволяет пользователю выбрать токен для сбора"""
    if not token_list:
        logger.error('Нет доступных токенов для выбора')
        return None
    
    logger.info('=== ВЫБОР ТОКЕНА ДЛЯ СБОРА ===\n')
    
    while True:
        try:
            choice = input(f'Введите номер токена (1-{len(token_list)}) или 0 для ввода своего адреса: ').strip()
            
            if choice == '0':
                # Пользователь хочет ввести свой адрес
                custom_address = input('Введите адрес токена (0x...): ').strip()
                if Web3.is_address(custom_address):
                    return {
                        'address': Web3.to_checksum_address(custom_address),
                        'type': 'ERC-20'  # По умолчанию ERC-20
                    }
                else:
                    logger.error('Неверный формат адреса')
                    continue
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(token_list):
                selected = token_list[choice_num - 1]
                logger.info(f'\nВыбран: {selected["symbol"]} ({selected["name"]})')
                logger.info(f'Тип: {selected.get("type", "ERC-20")}')
                logger.info(f'Адрес: {selected["address"]}')
                if selected.get("type") == "ERC-721":
                    logger.info(f'Всего NFT: {int(selected["total_balance"])}\n')
                else:
                    logger.info(f'Общий баланс: {selected["total_balance"]:.6f}\n')
                return {
                    'address': selected['address'],
                    'type': selected.get('type', 'ERC-20'),
                    'symbol': selected.get('symbol', ''),
                    'name': selected.get('name', '')
                }
            else:
                logger.error(f'Неверный номер. Введите число от 1 до {len(token_list)}')
        except ValueError:
            logger.error('Пожалуйста, введите число')
        except KeyboardInterrupt:
            logger.info('\nОтменено пользователем')
            return None


def send_erc20_transaction(provider, account, recipient_address, token_address, balance):
    """Отправляет транзакцию с ERC-20 токеном"""
    try:
        # Создаем контракт
        contract = provider.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
        
        # Получаем nonce
        nonce = provider.eth.get_transaction_count(account.address)
        
        # Строим транзакцию
        gas_price = Web3.to_wei(float(GAS_PRICE), 'gwei')
        
        transaction = contract.functions.transfer(
            Web3.to_checksum_address(recipient_address),
            balance
        ).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': GAS_LIMIT,
            'gasPrice': gas_price,
        })
        
        # Подписываем транзакцию
        signed_txn = account.sign_transaction(transaction)
        
        # Отправляем транзакцию
        tx_hash = provider.eth.send_raw_transaction(signed_txn.rawTransaction)
        logger.info(f"Транзакция отправлена. Hash: {tx_hash.hex()}")
        
        # Ждем подтверждения
        receipt = provider.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info(f"Транзакция подтверждена. Блок: {receipt['blockNumber']}")
        
        return {'success': True, 'txHash': tx_hash.hex(), 'receipt': receipt}
    except Exception as e:
        logger.error(f"Ошибка при отправке токена: {e}")
        return {'success': False, 'error': str(e)}


def get_nft_token_ids(provider, address, nft_address):
    """Получает список ID NFT токенов на кошельке"""
    try:
        contract = provider.eth.contract(
            address=Web3.to_checksum_address(nft_address),
            abi=ERC721_ABI
        )
        
        balance = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
        token_ids = []
        
        for i in range(balance):
            try:
                token_id = contract.functions.tokenOfOwnerByIndex(
                    Web3.to_checksum_address(address),
                    i
                ).call()
                token_ids.append(token_id)
            except Exception as e:
                logger.debug(f"Ошибка при получении token ID {i}: {e}")
        
        return token_ids
    except Exception as e:
        logger.error(f"Ошибка при получении NFT токенов: {e}")
        return []


def send_nft_transaction(provider, account, recipient_address, nft_address, token_id):
    """Отправляет NFT (ERC-721) транзакцию"""
    try:
        # Создаем контракт
        contract = provider.eth.contract(
            address=Web3.to_checksum_address(nft_address),
            abi=ERC721_ABI
        )
        
        # Получаем nonce
        nonce = provider.eth.get_transaction_count(account.address)
        
        # Строим транзакцию
        gas_price = Web3.to_wei(float(GAS_PRICE), 'gwei')
        
        transaction = contract.functions.transferFrom(
            account.address,
            Web3.to_checksum_address(recipient_address),
            token_id
        ).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': GAS_LIMIT,
            'gasPrice': gas_price,
        })
        
        # Подписываем транзакцию
        signed_txn = account.sign_transaction(transaction)
        
        # Отправляем транзакцию
        tx_hash = provider.eth.send_raw_transaction(signed_txn.rawTransaction)
        logger.info(f"Транзакция NFT отправлена. Hash: {tx_hash.hex()}")
        
        # Ждем подтверждения
        receipt = provider.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logger.info(f"Транзакция подтверждена. Блок: {receipt['blockNumber']}")
        
        return {'success': True, 'txHash': tx_hash.hex(), 'receipt': receipt}
    except Exception as e:
        logger.error(f"Ошибка при отправке NFT: {e}")
        return {'success': False, 'error': str(e)}


def collect_funds():
    """Основная функция сборщика"""
    logger.info('=== ЗАПУСК СБОРЩИКА СРЕДСТВ ===')
    
    # Загружаем приватные ключи
    private_keys = load_private_keys()
    
    if not private_keys:
        logger.error('ОШИБКА: Не указаны приватные ключи в .env файле')
        return
    
    if not RECIPIENT_ADDRESS or RECIPIENT_ADDRESS == '0x...':
        logger.error('ОШИБКА: Не указан адрес кошелька-получателя в config.py')
        return
    
    logger.info(f'Всего кошельков для проверки: {len(private_keys)}')
    logger.info(f'Целевой кошелек: {RECIPIENT_ADDRESS}\n')
    
    # Получаем провайдера
    try:
        provider = get_provider()
    except Exception as e:
        logger.error(f'Критическая ошибка: {e}')
        return
    
    # Создаем аккаунты из приватных ключей
    accounts = []
    for private_key in private_keys:
        private_key = private_key.strip()
        if private_key and not private_key.startswith('//') and not private_key.startswith('#'):
            try:
                account = provider.eth.account.from_key(private_key)
                accounts.append(account)
            except Exception as e:
                logger.warn(f'Ошибка при создании аккаунта из ключа: {e}')
    
    if not accounts:
        logger.error('Не удалось создать ни одного аккаунта')
        return
    
    # Сканируем все кошельки для поиска токенов
    all_tokens = scan_all_wallets(provider, accounts)
    
    # Отображаем найденные токены
    token_list = display_available_tokens(all_tokens)
    
    # Пользователь выбирает токен для сбора
    selected_token = select_token(token_list)
    
    if not selected_token:
        logger.info('Сбор отменен')
        return
    
    token_address = selected_token['address']
    token_type = selected_token.get('type', 'ERC-20')
    
    # Если выбран BASE, нужна особая обработка
    if token_address == 'BASE':
        logger.error('Сбор нативного токена BASE пока не поддерживается. Выберите ERC-20 токен или NFT.')
        return
    
    logger.info(f'\n=== НАЧАЛО СБОРА ===')
    logger.info(f'Тип: {token_type}')
    logger.info(f'Токен: {selected_token.get("symbol", "")} ({selected_token.get("name", "")})')
    logger.info(f'Адрес: {token_address}')
    logger.info(f'Целевой кошелек: {RECIPIENT_ADDRESS}\n')
    
    # Статистика
    total_processed = 0
    total_collected_tokens = 0
    total_collected_nft = 0
    success_count = 0
    error_count = 0
    
    # Обрабатываем каждый кошелек
    for i, account in enumerate(accounts):
        address = account.address
        
        logger.info(f'\n--- Кошелек {i + 1}/{len(accounts)}: {address} ---')
        
        try:
            if token_type == 'ERC-20':
                # Получаем баланс токена
                balance, decimals = get_token_balance(provider, address, token_address)
                balance_formatted = balance / (10 ** decimals)
                
                logger.info(f'Баланс токена: {balance_formatted:.6f}')
                
                if balance > 0:
                    # Отправляем токен
                    result = send_erc20_transaction(
                        provider, account, RECIPIENT_ADDRESS, token_address, balance
                    )
                    
                    if result['success']:
                        success_count += 1
                        total_collected_tokens += balance_formatted
                        logger.info(f'✓ Успешно собрано {balance_formatted:.6f} токенов')
                    else:
                        error_count += 1
                        logger.error(f'✗ Ошибка при отправке токена: {result.get("error", "Неизвестная ошибка")}')
                else:
                    logger.warn('Баланс токена равен нулю. Пропуск.')
            
            elif token_type == 'ERC-721':
                # Получаем список NFT
                token_ids = get_nft_token_ids(provider, address, token_address)
                
                if not token_ids:
                    logger.warn('NFT не найдены на кошельке. Пропуск.')
                    total_processed += 1
                    continue
                
                logger.info(f'Найдено NFT: {len(token_ids)}')
                
                # Отправляем каждую NFT
                for token_id in token_ids:
                    logger.info(f'Отправка NFT с ID: {token_id}')
                    result = send_nft_transaction(
                        provider, account, RECIPIENT_ADDRESS, token_address, token_id
                    )
                    
                    if result['success']:
                        success_count += 1
                        total_collected_nft += 1
                        logger.info(f'✓ Успешно отправлена NFT #{token_id}')
                    else:
                        error_count += 1
                        logger.error(f'✗ Ошибка при отправке NFT #{token_id}: {result.get("error", "Неизвестная ошибка")}')
                    
                    # Задержка между отправками NFT
                    if token_ids.index(token_id) < len(token_ids) - 1:
                        time.sleep(DELAY / 1000.0)
            else:
                logger.warn(f'Тип токена {token_type} пока не поддерживается')
            
            total_processed += 1
            
            # Задержка между кошельками
            if i < len(accounts) - 1:
                logger.debug(f'Задержка {DELAY} мс перед следующим кошельком...')
                time.sleep(DELAY / 1000.0)
        
        except Exception as e:
            error_count += 1
            logger.error(f'Ошибка при обработке кошелька {i + 1}: {e}')
            continue
    
    # Выводим статистику
    logger.info('\n=== СТАТИСТИКА ===')
    logger.info(f'Обработано кошельков: {total_processed}')
    logger.info(f'Успешных транзакций: {success_count}')
    logger.info(f'Ошибок: {error_count}')
    if token_type == 'ERC-20':
        logger.info(f'Всего собрано токенов: {total_collected_tokens:.6f}')
    elif token_type == 'ERC-721':
        logger.info(f'Всего собрано NFT: {total_collected_nft}')
    logger.info('=== ЗАВЕРШЕНО ===')


if __name__ == '__main__':
    try:
        collect_funds()
    except KeyboardInterrupt:
        logger.info('\nПрервано пользователем')
        sys.exit(0)
    except Exception as e:
        logger.error(f'Критическая ошибка при выполнении программы: {e}')
        sys.exit(1)

