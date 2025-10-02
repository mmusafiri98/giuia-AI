"""
Script per trovare gli endpoint API di uno Space HuggingFace
Esegui: python check_api.py
"""

from gradio_client import Client

def check_space_api(space_id):
    """Trova tutti gli endpoint disponibili in uno space"""
    print(f"\n🔍 Controllo Space: {space_id}")
    print("=" * 60)
    
    try:
        client = Client(space_id)
        
        # Ottieni info sugli endpoint
        print("\n📋 Endpoint disponibili:")
        print("-" * 60)
        
        # Prova a vedere gli endpoint
        if hasattr(client, 'endpoints'):
            for endpoint in client.endpoints:
                print(f"  ✅ {endpoint}")
        
        # Prova metodo alternativo
        if hasattr(client, 'view_api'):
            print("\n📄 API Info:")
            print(client.view_api())
        
        # Info client
        print(f"\n📊 Info Client:")
        print(f"  Space: {space_id}")
        print(f"  Type: {type(client)}")
        
        # Lista attributi utili
        useful_attrs = ['predict', 'submit', 'endpoints', 'api_name']
        print(f"\n🔧 Metodi disponibili:")
        for attr in dir(client):
            if not attr.startswith('_') and attr in useful_attrs:
                print(f"  - {attr}")
        
        return True
        
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

# Space da controllare
SPACES_TO_CHECK = [
    "Lightricks/ltx-video-distilled",
    "multimodalart/stable-video-diffusion",
    "guoyww/animatediff"
]

if __name__ == "__main__":
    print("=" * 60)
    print("🔎 SPACE API CHECKER")
    print("=" * 60)
    
    for space in SPACES_TO_CHECK:
        check_space_api(space)
        print("\n" + "=" * 60)
    
    print("\n💡 Suggerimenti:")
    print("1. Gli endpoint di solito sono: /predict, /generate, /inference")
    print("2. Controlla la documentazione dello Space su HuggingFace")
    print("3. Prova diversi api_name se uno non funziona")
    print("\n✅ Test completato!")
