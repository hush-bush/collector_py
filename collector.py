#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборщик средств для сети Base
Собирает токены с нескольких кошельков на один целевой кошелек
"""

import os
import sys
import time
from web3 import Web3
from config import (
    RPC_URL, ALTERNATIVE_RPC_URLS, RECIPIENT_ADDRESS,
    TOKEN_ADDRESS, GAS_PRICE, GAS_LIMIT, DELAY
)

# ERC-20 ABI (минимальный для работы с балансом и transfer)
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
    }
]


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


def send_token_transaction(provider, account, recipient_address, token_address, balance):
    """Отправляет транзакцию с токеном"""
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


def collect_funds():
    """Основная функция сборщика"""
    logger.info('=== ЗАПУСК СБОРЩИКА СРЕДСТВ ===')
    logger.info(f'Целевой кошелек: {RECIPIENT_ADDRESS}')
    logger.info(f'Токен: {TOKEN_ADDRESS}')
    
    # Загружаем приватные ключи
    private_keys = load_private_keys()
    
    if not private_keys:
        logger.error('ОШИБКА: Не указаны приватные ключи в .env файле')
        return
    
    if not RECIPIENT_ADDRESS or RECIPIENT_ADDRESS == '0x...':
        logger.error('ОШИБКА: Не указан адрес кошелька-получателя в config.py')
        return
    
    logger.info(f'Всего кошельков для проверки: {len(private_keys)}')
    logger.info('')
    
    # Получаем провайдера
    try:
        provider = get_provider()
    except Exception as e:
        logger.error(f'Критическая ошибка: {e}')
        return
    
    # Статистика
    total_processed = 0
    total_collected_tokens = 0
    success_count = 0
    error_count = 0
    
    # Обрабатываем каждый кошелек
    for i, private_key in enumerate(private_keys):
        private_key = private_key.strip()
        
        if not private_key or private_key.startswith('//') or private_key.startswith('#'):
            logger.debug(f'Пропуск пустой или закомментированной строки {i + 1}')
            continue
        
        logger.debug(f'Обработка кошелька {i + 1} из {len(private_keys)}')
        
        try:
            # Создаем аккаунт из приватного ключа
            account = provider.eth.account.from_key(private_key)
            address = account.address
            
            logger.info(f'\n--- Кошелек {i + 1}: {address} ---')
            
            # Получаем баланс токена
            balance, decimals = get_token_balance(provider, address, TOKEN_ADDRESS)
            balance_formatted = balance / (10 ** decimals)
            
            logger.info(f'Баланс токена: {balance_formatted}')
            
            if balance > 0:
                # Отправляем токен
                result = send_token_transaction(
                    provider, account, RECIPIENT_ADDRESS, TOKEN_ADDRESS, balance
                )
                
                if result['success']:
                    success_count += 1
                    total_collected_tokens += balance_formatted
                    logger.info(f'✓ Успешно собрано {balance_formatted} токенов')
                else:
                    error_count += 1
                    logger.error(f'✗ Ошибка при отправке токена: {result.get("error", "Неизвестная ошибка")}')
            else:
                logger.warn('Баланс токена равен нулю. Пропуск.')
            
            total_processed += 1
            
            # Задержка между транзакциями
            if i < len(private_keys) - 1:
                logger.debug(f'Задержка {DELAY} мс перед следующей транзакцией...')
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
    logger.info(f'Всего собрано токенов: {total_collected_tokens:.6f}')
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

