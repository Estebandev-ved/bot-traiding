#!/usr/bin/env python3
"""
Script para obtener nuevas claves de Binance Testnet
"""

def mostrar_instrucciones():
    """Muestra las instrucciones para obtener claves de testnet"""
    
    print("="*70)
    print("INSTRUCCIONES PARA OBTENER CLAVES DE BINANCE TESTNET")
    print("="*70)
    print()
    print("1. Ve a: https://testnet.binance.vision/")
    print("2. Haz clic en 'Generate HMAC_SHA256 Key'")
    print("3. Copia la API Key y API Secret que se generan")
    print("4. Edita el archivo 'config.env' y reemplaza:")
    print()
    print("   BINANCE_TESTNET_API_KEY=tu_nueva_api_key_aqui")
    print("   BINANCE_TESTNET_API_SECRET=tu_nueva_api_secret_aqui")
    print()
    print("5. Guarda el archivo y ejecuta: python test_connection.py")
    print()
    print("IMPORTANTE:")
    print("- Las claves de testnet son GRATUITAS")
    print("- Solo funcionan en el entorno de pruebas")
    print("- No necesitas verificar identidad")
    print("- Se regeneran cada vez que visitas la pagina")
    print()
    print("="*70)

if __name__ == "__main__":
    mostrar_instrucciones()
    
    # Preguntar si quiere abrir la página
    respuesta = input("¿Quieres abrir la página de testnet ahora? (s/n): ").lower()
    if respuesta in ['s', 'si', 'sí', 'y', 'yes']:
        import webbrowser
        webbrowser.open("https://testnet.binance.vision/")
        print("Página abierta en tu navegador.")
    else:
        print("Puedes abrir manualmente: https://testnet.binance.vision/")
