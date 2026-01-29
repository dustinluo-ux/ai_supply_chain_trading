"""
Test Gemini API connection with proxy disabled
This script temporarily disables proxy environment variables and tests the Gemini API
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_gemini_connection():
    """Test Gemini API connection with proxy disabled"""
    
    print("=" * 60)
    print("Gemini API Connection Test")
    print("=" * 60)
    
    # Check current proxy settings
    print("\n[1] Current Proxy Settings:")
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
    for var in proxy_vars:
        value = os.environ.get(var, 'Not set')
        print(f"  {var}: {value}")
    
    # Save original values
    original_proxies = {}
    for var in proxy_vars:
        original_proxies[var] = os.environ.get(var)
    
    # Disable proxy for this test
    print("\n[2] Disabling proxy environment variables...")
    for var in proxy_vars:
        os.environ.pop(var, None)
        print(f"  [OK] Unset {var}")
    
    # Check API key
    print("\n[3] Checking API Key:")
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        print(f"  [OK] API Key found: {api_key[:10]}...{api_key[-4:]}")
    else:
        print("  [ERROR] API Key not found in environment!")
        return False
    
    # Test Gemini API
    print("\n[4] Testing Gemini API Connection:")
    try:
        import google.generativeai as genai
        
        print("  - Configuring Gemini client...")
        genai.configure(api_key=api_key)
        
        print("  - Creating model instance...")
        # Try gemini-2.0-flash first, fallback to exp
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            print("  [OK] Using model: gemini-2.0-flash")
        except Exception as e:
            print(f"  - gemini-2.0-flash not available, trying exp version...")
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            print("  [OK] Using model: gemini-2.0-flash-exp")
        
        print("  - Sending test request...")
        response = model.generate_content(
            "Say 'Hello, Gemini API is working!' in exactly 5 words.",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=50
            )
        )
        
        print(f"  [OK] Response received: {response.text}")
        print("\n" + "=" * 60)
        print("[SUCCESS] Gemini API connection is working!")
        print("=" * 60)
        
        # Restore original proxy settings
        print("\n[5] Restoring original proxy settings...")
        for var, value in original_proxies.items():
            if value is not None:
                os.environ[var] = value
                print(f"  [OK] Restored {var}")
            else:
                print(f"  - {var} was not set originally")
        
        return True
        
    except ImportError:
        print("  [ERROR] google-generativeai not installed!")
        print("  Install with: pip install google-generativeai")
        return False
        
    except Exception as e:
        print(f"  [ERROR] Connection failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        print("\n  Full traceback:")
        traceback.print_exc()
        
        # Restore original proxy settings
        print("\n[5] Restoring original proxy settings...")
        for var, value in original_proxies.items():
            if value is not None:
                os.environ[var] = value
        
        return False

if __name__ == "__main__":
    success = test_gemini_connection()
    sys.exit(0 if success else 1)
