import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

dotenv_utils_path = os.path.join(os.path.dirname(__file__), ".pass")
load_dotenv(dotenv_utils_path)
email_base = os.getenv("QWEN_EMAIL")
password = os.getenv("QWEN_PASSWORD")

url = "https://chat.qwen.ai/api/v1/auths/signin"
headers = {
    "Content-Type": "application/json",
    "Origin": "https://chat.qwen.ai",
    "Referer": "https://chat.qwen.ai/",
    "User-Agent": "Mozilla/5.0",
}

tokens = []

async def cleanup_history_and_memory(session, token):
    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    results = {}
    
    delete_url = "https://qwen.aikit.club/v1/chats/delete"
    try:
        async with session.delete(delete_url, headers=auth_headers) as resp:
            results['delete_chats'] = {
                'status': resp.status,
                'success': resp.status == 200
            }
            if resp.status != 200:
                try:
                    results['delete_chats']['error'] = await resp.text()
                except:
                    results['delete_chats']['error'] = 'Failed to read error response'
    except Exception as e:
        results['delete_chats'] = {
            'status': 'error',
            'success': False,
            'error': str(e)
        }
    
    await asyncio.sleep(0.5)
    
    memory_settings_payload = {
        "memory": {
            "enable_memory": False,
            "enable_history_memory": False,
            "memory_version_reminder": False
        }
    }
    
    try:
        async with session.post(
            'https://chat.qwen.ai/api/v2/users/user/settings/update',
            json=memory_settings_payload,
            headers=auth_headers
        ) as resp:
            results['memory_settings'] = {
                'status': resp.status,
                'success': resp.status == 200
            }
            if resp.status != 200:
                try:
                    results['memory_settings']['error'] = await resp.text()
                except:
                    results['memory_settings']['error'] = 'Failed to read error response'
    except Exception as e:
        results['memory_settings'] = {
            'status': 'error',
            'success': False,
            'error': str(e)
        }
    
    return results

async def process_account(email, password, session, account_num):
    payload = {"email": email, "password": password}
    account_info = {"email": email, "account_num": account_num}
    
    try:
        response = await session.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = await response.json()
        token = data.get("token")
        
        if token:
            account_info['token'] = token
            account_info['auth_success'] = True
            
            cleanup_results = await cleanup_history_and_memory(session, token)
            account_info['cleanup_results'] = cleanup_results
            
            return account_info
        else:
            account_info['auth_success'] = False
            account_info['error'] = "No token in response"
            return account_info
            
    except Exception as e:
        account_info['auth_success'] = False
        account_info['error'] = str(e)
        return account_info

async def main():
    global tokens
    
    connector = aiohttp.TCPConnector(limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        for i in range(10):
            email = email_base if i == 0 else email_base.replace("@", f"+{i}@")
            tasks.append(process_account(email, password, session, i))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_tokens = []
        failed_accounts = []
        
        print("\n" + "="*60)
        print("РЕЗУЛЬТАТЫ ОБРАБОТКИ АККАУНТОВ")
        print("="*60)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"\n❌ Аккаунт {i}: Ошибка - {result}")
                failed_accounts.append({"account_num": i, "error": str(result)})
                continue
                
            email = result['email']
            account_num = result['account_num']
            
            if result.get('auth_success'):
                token = result['token']
                cleanup_results = result.get('cleanup_results', {})
                
                successful_tokens.append({"bearer": token})
                
                print(f"\n✅ Аккаунт {account_num} ({email}):")
                print(f"   Токен получен: Да")
                
                if cleanup_results.get('delete_chats'):
                    delete_res = cleanup_results['delete_chats']
                    status = "✅ Успешно" if delete_res.get('success') else "❌ Ошибка"
                    print(f"   Очистка истории: {status} (Статус: {delete_res.get('status')})")
                
                if cleanup_results.get('memory_settings'):
                    mem_res = cleanup_results['memory_settings']
                    status = "✅ Успешно" if mem_res.get('success') else "❌ Ошибка"
                    print(f"   Настройка памяти: {status} (Статус: {mem_res.get('status')})")
            else:
                print(f"\n❌ Аккаунт {account_num} ({email}):")
                print(f"   Ошибка авторизации: {result.get('error', 'Unknown error')}")
                failed_accounts.append({
                    "account_num": account_num, 
                    "email": email, 
                    "error": result.get('error', 'Unknown error')
                })
        
        print("\n" + "="*60)
        print(f"ИТОГО: {len(successful_tokens)} успешных, {len(failed_accounts)} неудачных")
        print("="*60)
        
        tokens = successful_tokens
        
        if failed_accounts:
            failed_path = os.path.join(os.path.dirname(__file__), "failed_accounts.json")
            with open(failed_path, "w", encoding="utf-8") as f:
                json.dump(failed_accounts, f, ensure_ascii=False, indent=2)
            print(f"Информация о неудачных аккаунтах сохранена в {failed_path}")

asyncio.run(main())

if tokens:
    tokens_json = json.dumps(tokens, ensure_ascii=False)
    main_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    env_key = "QWEN_ACCS"
    new_line = f'{env_key}={tokens_json}\n'
    
    if os.path.exists(main_env_path):
        with open(main_env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_key}="):
                lines[i] = new_line
                updated = True
                break
        
        if not updated:
            lines.append(new_line)
    else:
        lines = [new_line]
    
    with open(main_env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    print(f"\n✅ Успешно обработано {len(tokens)} аккаунтов")
    print(f"✅ QWEN_ACCS успешно обновлён в {main_env_path}")
else:
    print("\n❌ Не удалось получить ни одного токена")