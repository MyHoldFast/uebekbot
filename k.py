import requests

cookies = {
   'ssxmod_itna': '1-QqAxyiGQiQK7Txe94mwqQK0QDtHi=HtoDzxC5iOD_xQ5DODLxnb4Gdqndq6w=zWdzb70044dDDqXhlD050rDmqi12DYPGfKPk2ImdC7BA5GdC3l5NNqC0Cwq4tauUGxI565s0I9tlmvZKshHbtQ4DHxi8DB9DmlcYDeeDtx0rD0eDPxDYDG4DoEYDn14DjxDd84SAmROaDm_IHxDbDimIW4aeDD5DAhBPLngrDGyrKsextDgD0bd_i1RPhtD6djGID7y3Dlp5ksmISR6y5h36Wk6LQroDX2tDvrSoEfBPnnEfpSSYoDHVwmmejhrBvC0P3iGwjK4Q_ebhhQeNGGrQDqBh=im=QDZ0qD92mDDAB2rFDN3O4b_r3WMGvlAvZK2Dk0GKeP=i4CG7CDKEDN77N/ri9i4aqqZhPti44_5TDPeD',
    'ssxmod_itna2': '1-QqAxyiGQiQK7Txe94mwqQK0QDtHi=HtoDzxC5iOD_xQ5DODLxnb4Gdqndq6w=zWdzb70044dDDqXhwDDcAeq9mnAqDLQ0TaNk87DDs2QW=9_LoDTOQxuGyAUSKq5Zzl8a4uLk10geaHjyOp2DkcpGklrHaeI71EcBsyrG_uWpqYBc82eAHOPKkYZKFzpGvp=04m8a1oUSskQOQqjB1u6OajzKOc28j3GMazDF4UtmHhzfGubF0z=e6qihuFo9DuZ0_osjxO69409o0PBpkjtvsgbSkejx7pO7_Rfca6k7Sc1ihy2o/OxgDu3z/qrSfQPh=2OQoBH=0x5TTo0Ni3KzdYqMtjhO/MQco5OjQzd_WRG52hQLtKiH/rkm2qFE4hnx94oEh_NfGe3QLOCh2=2YYOmNfo1u0Te7wGOOLxNGrTu_Em23a3zDbWCCQp2_cEb78L/xTWWhbCbk1=_YEwOFzGj7ZtZx7Y2xtnNd1tOxEbl3tnweWaVE8Z2=QfNEo_jOhVONq0dFEkbM1yoreqtj2qq_TFzrMlQV42oSkVr_447iGbMoaiWn5LI7g0dLXcjXh=KUxft1r52F/hOR2Of=GvOdnw=LOp5ObMCrFT1K_DTfQ2BINh4q0xlAQegL_gjh38/EWHOx0l7v_4sNdHS7j_4Oo5mnDdFlHhZVxa0gdh8q5SNe7FZi7R5HGYIyansfHxSNOx2i1m54KQahxntgvNjYzFtDGp2Kihrn8mbw02pbDYqFbMpxY=5hKzQkiZmqkqOxekq5he4RNi5dGG7_nh57_4urWenhcYYkh=4xGq3tDw0D7DsYTFe3hNDe54zBxPDTIeY2cZh4D',
}

headers = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5,ja;q=0.4,de;q=0.3',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Origin': 'https://chat.qwen.ai',
    'Pragma': 'no-cache',
    'Referer': 'https://chat.qwen.ai/c/2412f2a1-b964-4af7-a2a4-6cc2e213df13',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImE4YTc3NmEzLWQ0NzItNDdlYi04YzMyLTNkNGUxNjE2Mzg4OSIsImxhc3RfcGFzc3dvcmRfY2hhbmdlIjoxNzUwNjYwODczLCJleHAiOjE3NTk3NTc1NzJ9.aP-JmOqGkfAbaRHOth_xdJ-i3JZjQFAMVLkPhJZoI_Y',
    'bx-ua': '231!cGG3N4mUI0S+j3q4E+3N0LEjUq/YvqY2leOxacSC80vTPuB9lMZY9mRWFzrwLEV0PmcfY4rL2l/3tvLpMixvmLs4/dJSz0t1vc7YklXEtL8pkK9EFFfw0gJWYCcYa3hK3l/cGDuw+zd+xTgDK8e5yPbCD0oyUU0a0Y22idh7TddWeyKxXadoHvAk1duC3nxtbTYuv9dzp+EVcXUFb1AOgU4URSCHv/6yesVElYSM3km+0Q3oyE+jauHhUilOz4MGHkE+++3+qCS4+ItNdAVFqoQso+r+JbkdTY3U//2KdFHC4tnMsS6EVjrsafsxi/wmWNAKBZdAEEk6rNuY4Aa5A6sxSHh9aq7C7XaX+PxBGAYMb/CNjEerQoRWKVjtBW+A/p0nX6kJBRoa6MgWppKk99L949pvXBYjePIW2a7LXn52uzYEZAXlO/S/355UC2FBy1H47j6oO5YvxpY5WePz0rS3OR04UH2aE0WJvACDmJTkw5aRoKWU804hqTZKo9pQSFfsA7okvDlN7UiIGqZcJeLT/mJq8JpWfAK9K9CNYhHDlvLI2sdR5VmzaZT63TOiD5cB8bFcPxUTEz5YuznJKPVbIX6HgIll37OTCTwdmo/3hapNzLXCPFyS5g1DHsQBIzLfFCN2cbD7Xjx9AstRI+RCB9zuBjDRBuk8sNihdjcxpJtclyFfyXkpR3bDo28LQGcIKtwa0LalHxx+KjEIbqXM95s2YPKUBUQJCWmgra3mHYae4Mkc+HAz3OUV7SbwJ3QCW8j1d6AH1SukgCXj+URz0JRazMAHPCvvIJ1ba9qsj5sF8wmSwy5JZuMGBRUze7LNS3J/OhQRqQLbV4IY8t1k36WZc1YC7FXd6ujTKqS39UmOAIp31MFXif/H4hV7Or0QyAEl9Vjhtf+m6tlp0aUaBkScOAxUZVqBh790kkyQuOf4ADQJsFgK5AYAkYOkhOeSjJy2iIhZBDWDtGwn6B9a9iBEd816m8lZjTZeUynjy9M5+pH4SniSytn5x/549PvHGUSiTKtMFq6K+6ah/7FKCVUTG+56D3FPGiIZ899US0VhEWUnTfOY/YvTWXRztFf00NYn9Se3DavW24Hkqmmd7spcciDsgTl40iSOJu0DbaIbY02NSxO14H4BXMg59XQ8DxnvuTN+tt0VgIbkgjWyWsm2SW9DFmdyzNZvHngXKXbWoiyYW+bKHUXcyX2pAmKj2EQ51cj9DewNiWGkkq5J3bgtufI5O9eQBGhnOWIQix6N7rCJurQ9LmnmuhNMjJDUDdJAHWv+QHk5T4YfX5nBfXQtV0tRmEGuK8f2d9ZGRnhLsLwfRwBilYOTbzHvC8wOvJqDGy5lG4oQEeRnh7tsqnCG2N+Da71ijHc2TASHKjIARecTsle+yjJjXLXGobXh/uxf8X2XL7OSR/T2dk5NBtyhg0Qk9PXyvm8OdrfcbLlA5aA19OG6YqOIjout7/+Occd9RQQnAY9xJ7UuQyHqpexhQ6q7dKWvwrZdmZtMhbNpCDAlwplzu6mHiTZEtH8Exai2tOgfbnYIus4I0vD9J8HclqYoV/8yGbcYmQ3Fg6PKSugQzRR6UYbMRZbNAdGMPyW+s47O7JYP99fpzdBjKPMsMCVZEOXXQxg1ny21xZ3rD1FA4NhldT3OnrpRWvYvkl0HP5lay8Q943L0L5BsU2i130xWU4==',
    'bx-umidtoken': 'T2gA0vIYCH63-9f8G-HkJxZ-QTRRf-SNPjQfr8zLFWFBdnp2Ftt9ByU8Zhjx4lhqX6w=',
    'bx-v': '2.5.31',
    'content-type': 'application/json; charset=UTF-8',
    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'source': 'web',
    'timezone': 'Mon Sep 29 2025 16:34:00 GMT+0300',
    'x-accel-buffering': 'no',
}

params = {
    'chat_id': '2412f2a1-b964-4af7-a2a4-6cc2e213df13',
}

json_data = {
    'stream': False,
    'incremental_output': True,
    'chat_id': '2412f2a1-b964-4af7-a2a4-6cc2e213df13',
    'chat_mode': 'normal',
    'model': 'qwen3-max',
    'messages': [
        {
            
            'role': 'user',
            'content': 'ещё',
            'user_action': 'chat',
            'files': [],
            'models': [
                'qwen3-max',
            ],
            'chat_type': 't2t',
            'feature_config': {
                'thinking_enabled': False,
                'output_schema': 'phase',
            },
            'extra': {
                'meta': {
                    'subChatType': 't2t',
                },
            },
            'sub_chat_type': 't2t'
        },
    ],
}

response = requests.post(
    'https://chat.qwen.ai/api/v2/chat/completions',
    params=params,
    cookies=cookies,
    headers=headers,
    json=json_data,
)

print(response.text)

# Note: json_data will not be serialized by requests
# exactly as it was in the original request.
#data = '{"stream":true,"incremental_output":true,"chat_id":"2412f2a1-b964-4af7-a2a4-6cc2e213df13","chat_mode":"normal","model":"qwen3-max","parent_id":"d78a3931-514a-4f66-abb1-bffaa3fd6059","messages":[{"fid":"2af8c961-1729-4dea-94c6-1336ba521f2f","parentId":"d78a3931-514a-4f66-abb1-bffaa3fd6059","childrenIds":["db55a199-c599-4a3e-bf5e-cb243cfa5d1f"],"role":"user","content":"куку","user_action":"chat","files":[],"timestamp":1759152840,"models":["qwen3-max"],"chat_type":"t2t","feature_config":{"thinking_enabled":false,"output_schema":"phase"},"extra":{"meta":{"subChatType":"t2t"}},"sub_chat_type":"t2t","parent_id":"d78a3931-514a-4f66-abb1-bffaa3fd6059"}],"timestamp":1759152840}'.encode()
#response = requests.post('https://chat.qwen.ai/api/v2/chat/completions', params=params, cookies=cookies, headers=headers, data=data)