import streamlit as st
import google.generativeai as genai
import pathlib
import json
import tempfile
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import time
import re
import mimetypes
import urllib.parse

# Load environment variables
load_dotenv()

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables. Please check your .env file.")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Xero API Configuration
XERO_CLIENT_ID = "AC7C52359BC24721BBC3B9E05624AA55"
XERO_CLIENT_SECRET = "7lOruP7EPO4SkCBKC4km0_4s6AojpetW0VQaVxLFpNx0Q26D"

# Global variables to store tokens
XERO_REFRESH_TOKEN = "jKnAS7ftPznEYT_mpVSkgIVMjmF7yU8bHjUUSeWJZI0"  # Initial refresh token
XERO_ACCESS_TOKEN = None
XERO_TENANT_ID = None

def load_refresh_token():
    """
    Load refresh token from JSON file if it exists
    """
    try:
        if os.path.exists("refresh_token.json"):
            with open("refresh_token.json", "r") as f:
                data = json.load(f)
                return data.get("refresh_token", XERO_REFRESH_TOKEN)
    except Exception as e:
        print(f"Error loading refresh token: {e}")
    return XERO_REFRESH_TOKEN

def save_refresh_token(token):
    """
    Save refresh token to JSON file with metadata
    """
    try:
        from datetime import datetime
        data = {
            "refresh_token": token,
            "last_updated": datetime.now().isoformat() + "Z",
            "client_id": XERO_CLIENT_ID,
            "client_secret": XERO_CLIENT_SECRET
        }
        with open("refresh_token.json", "w") as f:
            json.dump(data, f, indent=4)
        print(f"✅ Refresh token saved to JSON file")
    except Exception as e:
        print(f"Error saving refresh token: {e}")

# Load the stored refresh token
XERO_REFRESH_TOKEN = load_refresh_token()

class XeroTokenManager:
    def __init__(self):
        # Always use the current global refresh token
        global XERO_REFRESH_TOKEN
        self.refresh_token = XERO_REFRESH_TOKEN
        self.access_token = XERO_ACCESS_TOKEN
        self.tenant_id = XERO_TENANT_ID
        
    def refresh_access_token(self):
        """
        Refresh the access token using the stored refresh token
        """
        try:
            token_url = "https://identity.xero.com/connect/token"
            
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": XERO_CLIENT_ID,
                "client_secret": XERO_CLIENT_SECRET
            }
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            response = requests.post(token_url, data=payload, headers=headers)
            print(f"Token refresh status code: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                print("Token refresh successful")
                print(json.dumps(token_data, indent=4))
                
                # Update tokens
                old_refresh_token = self.refresh_token
                self.access_token = token_data.get("access_token")
                new_refresh_token = token_data.get("refresh_token")  # Save new refresh token
                
                # Update global variables
                global XERO_ACCESS_TOKEN, XERO_REFRESH_TOKEN
                XERO_ACCESS_TOKEN = self.access_token
                XERO_REFRESH_TOKEN = new_refresh_token
                self.refresh_token = new_refresh_token
                
                # Save the new refresh token to file
                save_refresh_token(new_refresh_token)
                
                print(f"🔄 Token Refresh Summary:")
                print(f"   Old Refresh Token: {old_refresh_token[:30]}...")
                print(f"   New Refresh Token: {new_refresh_token[:30]}...")
                print(f"   New Access Token: {self.access_token[:50]}...")
                print(f"   ✅ Tokens replaced and saved to file")
                
                return True
            else:
                print(f"❌ Token refresh failed: {response.status_code}")
                print(response.text)
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing token: {str(e)}")
            return False
    
    def get_tenant_id(self):
        """
        Get tenant ID using the current access token
        """
        if not self.access_token:
            print("❌ No access token available")
            return None
            
        try:
            url = "https://api.xero.com/connections"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json"
            }
            
            response = requests.get(url, headers=headers)
            print(f"Tenant ID request status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("Tenant ID request successful")
                print(json.dumps(data, indent=4))
                
                if data:
                    self.tenant_id = data[0]["tenantId"]
                    tenant_name = data[0]["tenantName"]
                    
                    # Update global variable
                    global XERO_TENANT_ID
                    XERO_TENANT_ID = self.tenant_id
                    
                    print(f"✅ Tenant ID: {self.tenant_id}")
                    print(f"✅ Tenant Name: {tenant_name}")
                    return self.tenant_id
                else:
                    print("⚠️ No connections found")
                    return None
            elif response.status_code == 401:
                print("⚠️ Access token expired, refreshing...")
                if self.refresh_access_token():
                    return self.get_tenant_id()  # Retry with new token
                else:
                    return None
            else:
                print(f"❌ Failed to get tenant ID: {response.status_code}")
                print(response.text)
                return None
                
        except Exception as e:
            print(f"❌ Error getting tenant ID: {str(e)}")
            return None
    
    def get_valid_credentials(self):
        """
        Get valid access token and tenant ID, refreshing if necessary
        """
        # If we don't have an access token, refresh it
        if not self.access_token:
            if not self.refresh_access_token():
                return None, None
        
        # If we don't have a tenant ID, get it
        if not self.tenant_id:
            if not self.get_tenant_id():
                return None, None
        
        return self.access_token, self.tenant_id

def get_fresh_xero_credentials():
    """
    Get fresh Xero access token and tenant ID using refresh token flow
    """
    try:
        token_manager = XeroTokenManager()
        access_token, tenant_id = token_manager.get_valid_credentials()
        
        if access_token and tenant_id:
            return access_token, tenant_id
        else:
            st.error("Failed to get valid Xero credentials")
            return None, None
            
    except Exception as e:
        st.error(f"Error getting Xero credentials: {str(e)}")
        return None, None

def test_token_refresh():
    """
    Test function to demonstrate token refresh and replacement
    """
    try:
        print("🧪 Testing Token Refresh Process...")
        
        # Create token manager
        token_manager = XeroTokenManager()
        print(f"Initial Refresh Token: {token_manager.refresh_token[:30]}...")
        
        # Attempt to refresh tokens
        success = token_manager.refresh_access_token()
        
        if success:
            print("✅ Token refresh test successful!")
            print(f"New Access Token: {token_manager.access_token[:50]}...")
            print(f"New Refresh Token: {token_manager.refresh_token[:30]}...")
            
            # Check if global variables were updated
            global XERO_ACCESS_TOKEN, XERO_REFRESH_TOKEN
            print(f"Global Access Token: {XERO_ACCESS_TOKEN[:50] if XERO_ACCESS_TOKEN else 'None'}...")
            print(f"Global Refresh Token: {XERO_REFRESH_TOKEN[:30]}...")
            
            # Check if file was updated
            try:
                with open("refresh_token.json", "r") as f:
                    file_data = json.load(f)
                file_token = file_data.get("refresh_token", "")
                last_updated = file_data.get("last_updated", "Unknown")
                print(f"File Refresh Token: {file_token[:30]}...")
                print(f"Last Updated: {last_updated}")
                
                if file_token == token_manager.refresh_token:
                    print("✅ File token matches instance token")
                else:
                    print("❌ File token does not match instance token")
                    
            except Exception as e:
                print(f"❌ Error reading token file: {e}")
                
            return True
        else:
            print("❌ Token refresh test failed!")
            return False
            
    except Exception as e:
        print(f"❌ Error in token refresh test: {e}")
        return False

def extract_raw_context_from_file(filepath: str, mime_type: str):
    """
    Extracts raw text and tables from any file (PDF, image, etc.)
    and returns JSON with document_type, raw_text, and tables.
    """
    try:
        # Check if file exists and has content
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            raise ValueError("File is empty")
        
        if file_size < 100:  # Very small files are likely corrupted
            raise ValueError("File appears to be corrupted (too small)")
        
        file_bytes = pathlib.Path(filepath).read_bytes()

        prompt = """
        You are an expert document analysis AI.

        Analyze the attached document or image.

        - Identify the type of document, if possible (e.g. invoice, contract, ID card, certificate, academic record, medical report, bank statement, resume, etc.)
        - Extract ALL readable text from the document, including:
          - Titles
          - Paragraphs
          - Headings
          - Tables (convert tables into a structured JSON format with rows and columns)
          - Captions
          - Footnotes
          - Any visible text

        Return your result in the following JSON structure:

        {
          "document_type": "<document type>",
          "raw_text": "<all extracted text in natural reading order>",
          "tables": [
            {
              "table_number": 1,
              "headers": ["Column1", "Column2", ...],
              "rows": [
                ["row1col1", "row1col2", ...],
                ...
              ]
            }
          ]
        }

        - If no tables exist, return an empty array for "tables".
        - If the document type cannot be determined, set document_type to "Unknown".

        CRITICAL: You must return ONLY valid JSON. Do not include any explanations, markdown formatting, or additional text. Start your response with { and end with }.
        """

        response = model.generate_content(
            [
                {"mime_type": mime_type, "data": file_bytes},
                prompt
            ],
            stream=False
        )

        # Print usage metadata for cost tracking
        print("Raw Data Extraction Usage:")
        print(response.usage_metadata)

    except FileNotFoundError as e:
        st.error(f"File error: {str(e)}")
        return None
    except ValueError as e:
        st.error(f"File validation error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return None

    try:
        # Clean the response text to ensure it's valid JSON
        response_text = response.text.strip()
        
        # Remove any markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Find the first { and last } to extract only the JSON part
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            response_text = response_text[start_idx:end_idx + 1]
        
        # Additional cleaning: remove any trailing characters after the last }
        # This handles cases where there might be invisible characters or extra text
        response_text = response_text.strip()
        
        # Try to find the actual end of JSON by counting braces
        brace_count = 0
        actual_end = -1
        for i, char in enumerate(response_text):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    actual_end = i
                    break
        
        if actual_end != -1:
            response_text = response_text[:actual_end + 1]
        
        # Check if cleaned text is empty
        if not response_text:
            st.error("Empty response after cleaning")
            return None
        
        json_result = json.loads(response_text)
        return json_result
    except Exception as e:
        st.error(f"JSON parsing error: {str(e)}")
        st.error("Raw Gemini response:")
        st.code(response.text, language="text")
        st.error("Cleaned response text:")
        st.code(response_text if 'response_text' in locals() else "No cleaned text", language="text")
        return None

def process_invoice_data(raw_data: dict, filepath: str = None, mime_type: str = None):
    """
    Processes raw extracted data AND original file to extract structured invoice information
    with Kuwaiti Dinar formatting rules. Uses both text extraction and visual analysis for accuracy.
    """
    # Prepare the raw data for the LLM
    raw_text = raw_data.get("raw_text", "")
    tables = raw_data.get("tables", [])
    
    # Convert tables to text representation
    tables_text = ""
    for i, table in enumerate(tables):
        tables_text += f"\nTable {i+1}:\n"
        if table.get('headers'):
            tables_text += f"Headers: {', '.join(table['headers'])}\n"
        if table.get('rows'):
            for row in table['rows']:
                tables_text += f"Row: {', '.join(str(cell) for cell in row)}\n"
    
    full_context = f"Raw Text:\n{raw_text}\n\nTables Data:\n{tables_text}"

    # Prepare the prompt for both text and visual analysis
    prompt = """
    You are an intelligent document parsing agent, responsible for accurately extracting structured data from invoice or receipt images, especially focused on Kuwaiti Dinar formatting, including split-number reconstruction.

    🇰🇼 Kuwaiti Dinar Amount Extraction (TOP PRIORITY):

    Instruction 1: Kuwaiti Dinar Amount Extraction
    - If a number is written as 4,90, 1,250, 3,400, 4,900, or similar, treat the comma (,) as a decimal point if it is separating dinars from fils.
    - The part before the comma is dinars; the part after the comma is fils.
    - Always express fils as 3 digits, zero-padded if needed:
        - E.g. "7,9" → "7.009" (seven dinars and nine fils)
        - E.g. "4,90" → "4.900" (four dinars and nine hundred fils)
        - E.g. "3,400" → "3.400" (three dinars and four hundred fils)
        - E.g. "4,900" → "4.900" (four dinars and nine hundred fils)
    - If there is no comma and no split (|), treat the entire number as dinars with zero fils:
        - E.g. "49" → "49.000"
    - Important Clarification:
        - If the number clearly represents a large amount written with a thousands separator (e.g. "4,900 KD"), interpret it as four thousand nine hundred dinars:
            - E.g. "4,900 KD" → "4900.000" (four thousand nine hundred dinars and zero fils)

    Instruction 2: Split Number Reconstruction
    If numbers appear across two adjacent columns or table cells, interpret them as:
    - Left = dinars
    - Right = fils
    - Combine them as <dinar>.<fils>
    - Zero-pad fils to 3 digits if fewer than 3 digits appear.

    Examples:
    - 24 | 500 → 24.500
    - 2 | 450 → 2.450
    - 1 | 50 → 1.050
    - 100 | 0 → 100.000
    - 7 | 9 → 7.009

    ⚠️ Split Number Rules:
    - Only use the two numeric parts directly adjacent to each other.
    - Do not extract values from neighboring lines or unrelated cells.
    - Ignore any currency symbols, extra labels, or formatting.
    - Focus only on numeric values from split cells.

    Instruction 3: Handling Single Numbers Without a Comma or Split
    - If there's no comma and no split (|), treat the entire number as dinars:
        - E.g. "47" → "47.000"
    - Do not assume any fils in such cases unless explicitly shown.

    Instruction 4: Customer Name Extraction
    - Extract the customer name from the invoice.
    - Look for fields labeled "Name:", "Customer:", "Client:", "Customer Name:", etc.
    - Also check for names near "NAME:" or similar labels.
    - If no customer name is found, return empty string "".

    Instruction 5: Date Extraction
    - Extract any invoice date, due date, or relevant date from the invoice.
    - Look for fields labeled "Date:", "Invoice Date:", "Due Date:", etc.
    - Format dates as either DD-MM-YYYY or YYYY-MM-DD.
    - If multiple dates exist, prioritize the invoice date.

    Instruction 5: Output Format
    Return the extracted information as valid JSON in this format:

    {
      "CompanyName": "",
      "CustomerName": "",
      "InvoiceNumber": "",
      "InvoiceDate": "",
      "Items": [
        {
          "Description": "",
          "Quantity": "",
          "Amount": ""
        }
      ],
      "GrandTotalExtracted": ""
    }

    Notes:
    - Note 1: All currency values must be strings, formatted with 3-digit fils, e.g., "24.500"
    - Note 2: No Inference — extract only visible data; do not calculate missing totals or sums.
    - Note 3: Field Handling — if any field is missing or not visible, return null or an empty string "" as appropriate.
    - Note 4: No Extra Output — return only valid JSON without explanations, sample data, or commentary.
    - Note 5: Items — extract only Description, Quantity, and Amount for each item. Skip UnitPrice if not needed.

    ✅ Final Examples:

    - "4,90" → "4.900"
    - "3,400" → "3.400"
    - "4,900" → "4.900"
    - "7,9" → "7.009"
    - "49" → "49.000"
    - "4,900 KD" → "4900.000" (four thousand nine hundred dinars and zero fils)
    - 24 | 500 → "24.500"
    - 2 | 450 → "2.450"
    - 1 | 50 → "1.050"
    - 100 | 0 → "100.000"
    - 7 | 9 → "7.009"

    CRITICAL: You must return ONLY valid JSON. Do not include any explanations, markdown formatting, or additional text. Start your response with { and end with }.

    Analyze the following extracted document data and return only valid JSON:

    """ + full_context

    # Use both text and visual analysis if file is provided
    if filepath and mime_type:
        try:
            file_bytes = pathlib.Path(filepath).read_bytes()
            response = model.generate_content(
                [
                    {"mime_type": mime_type, "data": file_bytes},
                    prompt
                ],
                stream=False
            )
        except Exception as e:
            st.error(f"Error reading file for visual analysis: {str(e)}")
            # Fallback to text-only analysis
            response = model.generate_content(prompt, stream=False)
    else:
        # Text-only analysis
        response = model.generate_content(prompt, stream=False)

    # Print usage metadata for cost tracking
    print("Invoice Processing Usage:")
    print(response.usage_metadata)

    try:
        # Check if response is empty or contains only whitespace
        if not response.text or response.text.strip() == "":
            st.error("Empty response from Gemini AI")
            return None
            
        # Clean the response text to ensure it's valid JSON
        response_text = response.text.strip()
        
        # Remove any markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Find the first { and last } to extract only the JSON part
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            response_text = response_text[start_idx:end_idx + 1]
        
        # Additional cleaning: remove any trailing characters after the last }
        # This handles cases where there might be invisible characters or extra text
        response_text = response_text.strip()
        
        # Try to find the actual end of JSON by counting braces
        brace_count = 0
        actual_end = -1
        for i, char in enumerate(response_text):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    actual_end = i
                    break
        
        if actual_end != -1:
            response_text = response_text[:actual_end + 1]
        
        # Check if cleaned text is empty
        if not response_text:
            st.error("Empty response after cleaning")
            return None
        
        json_result = json.loads(response_text)
        
        # Clean the data: remove items with NULL/empty Quantity
        if "Items" in json_result and isinstance(json_result["Items"], list):
            # Filter out items where Quantity is NULL, empty, or None
            cleaned_items = []
            for item in json_result["Items"]:
                if isinstance(item, dict):
                    quantity = item.get("Quantity", "")
                    # Keep item only if Quantity is not NULL, empty, or None
                    if quantity and quantity != "NULL" and quantity != "" and quantity is not None:
                        cleaned_items.append(item)
            
            json_result["Items"] = cleaned_items
        
        return json_result
    except Exception as e:
        st.error(f"JSON parsing error in invoice processing: {str(e)}")
        st.error("Raw Gemini response:")
        st.code(response.text, language="text")
        st.error("Cleaned response text:")
        st.code(response_text if 'response_text' in locals() else "No cleaned text", language="text")
        return None

def xero_payload(processed_data: dict):
    """
    Converts processed invoice data to Xero API payload format.
    """
    try:
        # Get current system date as fallback
        system_date = datetime.now().strftime("%Y-%m-%d")
        
        # Extract and convert invoice date
        invoice_date = processed_data.get("InvoiceDate", "")
        if invoice_date:
            # Try to parse and convert to YYYY-MM-DD format
            try:
                # Handle different date formats
                if "/" in invoice_date:
                    # Convert DD/MM/YYYY to YYYY-MM-DD
                    parts = invoice_date.split("/")
                    if len(parts) == 3:
                        if len(parts[2]) == 4:  # YYYY format
                            date_obj = datetime.strptime(invoice_date, "%d/%m/%Y")
                        else:  # YY format
                            date_obj = datetime.strptime(invoice_date, "%d/%m/%y")
                        invoice_date = date_obj.strftime("%Y-%m-%d")
                    else:
                        invoice_date = system_date
                elif "-" in invoice_date:
                    # Already in YYYY-MM-DD or DD-MM-YYYY format
                    if len(invoice_date.split("-")[0]) == 4:  # YYYY-MM-DD
                        invoice_date = invoice_date
                    else:  # DD-MM-YYYY
                        date_obj = datetime.strptime(invoice_date, "%d-%m-%Y")
                        invoice_date = date_obj.strftime("%Y-%m-%d")
                else:
                    invoice_date = system_date
            except:
                invoice_date = system_date
        else:
            invoice_date = system_date
        
        # Convert Items array to string
        items = processed_data.get("Items", [])
        items_string = json.dumps(items) if items else "[]"
        
        # Convert GrandTotalExtracted to float
        grand_total = processed_data.get("GrandTotalExtracted", "0")
        unit_amount = grand_total
        
        # Build Xero payload
        payload = {
            "Type": "ACCREC",
            "Contact": {
                "Name": processed_data.get("CompanyName", "")
            },
            "Date": invoice_date,
            "DueDate": "2025-07-15",
            "InvoiceNumber": processed_data.get("InvoiceNumber", ""),
            "LineAmountTypes": "Exclusive",
            "CurrencyCode": "KWD",
            "LineItems": [
                {
                    "Description": items_string,
                    "Quantity": 1.0,
                    "UnitAmount": unit_amount,
                    "AccountCode": "200",
                    "TaxType": "NONE"
                }
            ],
            "Status": "DRAFT"
        }
        
        return payload
        
    except Exception as e:
        st.error(f"Error creating Xero payload: {str(e)}")
        return None

def send_to_xero_api(xero_payload_data: dict):
    """
    Send the Xero payload to Xero API to create an invoice.
    """
    try:
        # Get fresh credentials
        with st.spinner("Getting fresh Xero credentials..."):
            access_token, tenant_id = get_fresh_xero_credentials()
        
        if not access_token or not tenant_id:
            return {"success": False, "error": "Failed to get Xero credentials"}

        # ✅ API endpoint
        url = "https://api.xero.com/api.xro/2.0/Invoices"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Xero-tenant-id": tenant_id
        }

        response = requests.post(url, headers=headers, json=xero_payload_data)

        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(json.dumps(result, indent=4))
                return {"success": True, "data": result, "status_code": response.status_code}
            except Exception as e:
                print("❌ Failed to parse JSON:", e)
                print(response.text)
                return {"success": False, "error": "Failed to parse JSON response", "text": response.text, "status_code": response.status_code}
        elif response.status_code == 401:
            # Token expired, refresh and retry
            print("⚠️ Access token expired, refreshing and retrying...")
            token_manager = XeroTokenManager()
            if token_manager.refresh_access_token():
                # Retry with new token
                new_access_token = token_manager.access_token
                headers["Authorization"] = f"Bearer {new_access_token}"
                
                retry_response = requests.post(url, headers=headers, json=xero_payload_data)
                print(f"Retry Status Code: {retry_response.status_code}")
                
                if retry_response.status_code == 200:
                    try:
                        result = retry_response.json()
                        print(json.dumps(result, indent=4))
                        return {"success": True, "data": result, "status_code": retry_response.status_code}
                    except Exception as e:
                        print("❌ Failed to parse JSON on retry:", e)
                        print(retry_response.text)
                        return {"success": False, "error": "Failed to parse JSON response on retry", "text": retry_response.text, "status_code": retry_response.status_code}
                else:
                    print("❌ API request failed on retry")
                    print(retry_response.text)
                    return {"success": False, "error": "API request failed on retry", "text": retry_response.text, "status_code": retry_response.status_code}
            else:
                return {"success": False, "error": "Failed to refresh access token", "status_code": response.status_code}
        else:
            print("❌ API request failed")
            print(response.text)
            return {"success": False, "error": "API request failed", "text": response.text, "status_code": response.status_code}
            
    except Exception as e:
        st.error(f"Error sending to Xero API: {str(e)}")
        return {"success": False, "error": str(e)}

# WhatsApp API Configuration
WHATSAPP_API_KEY = "D+bB8gKs.9LjARlG4zmh24vu5MIyv0iMYVXQinFcU6MVDCvG5C5U="
WHATSAPP_BASE_URL = "https://api15.unipile.com:14548/api/v1"

def validate_pdf_file(file_path):
    """
    Validate if a PDF file is readable and has content
    """
    try:
        import PyPDF2
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            if len(pdf_reader.pages) == 0:
                return False, "PDF file has no pages"
            return True, f"PDF file is valid with {len(pdf_reader.pages)} pages"
    except ImportError:
        # If PyPDF2 is not available, do basic file size check
        if os.path.getsize(file_path) < 100:  # Less than 100 bytes is likely corrupted
            return False, "File appears to be corrupted (too small)"
        return True, "File size check passed"
    except Exception as e:
        return False, f"Error validating PDF: {str(e)}"

def get_extension_from_mimetype(mimetype):
    """
    Guesses the file extension from mimetype.
    """
    if not mimetype:
        return ".bin"
    ext = mimetypes.guess_extension(mimetype)
    if ext:
        return ext
    return ".bin"

def decrypt_whatsapp_media(enc_filename, decrypted_filename, media_key_b64, media_type):
    """
    Decrypts WhatsApp media (document, image, video, etc.)
    """
    try:
        import base64
        from Crypto.Cipher import AES
        from Crypto.Protocol.KDF import HKDF
        from Crypto.Hash import SHA256
        
        media_key_bytes = base64.b64decode(media_key_b64)
        salt = b"\0" * 32

        # Decide info label based on media type
        info_labels = {
            "documentMessage": b"WhatsApp Document Keys",
            "imageMessage": b"WhatsApp Image Keys",
            "videoMessage": b"WhatsApp Video Keys",
            "audioMessage": b"WhatsApp Audio Keys",
            "stickerMessage": b"WhatsApp Image Keys",
        }

        info = info_labels.get(media_type, b"WhatsApp Media Keys")

        derived = HKDF(media_key_bytes, 112, salt, SHA256, context=info)
        iv = derived[0:16]
        aes_key = derived[16:48]

        with open(enc_filename, "rb") as f:
            enc_data = f.read()

        ciphertext = enc_data[:-10]  # Remove MAC
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        plaintext = cipher.decrypt(ciphertext)

        # Remove PKCS7 padding
        pad_len = plaintext[-1]
        plaintext = plaintext[:-pad_len]

        with open(decrypted_filename, "wb") as f:
            f.write(plaintext)

        return True, f"Decryption complete. Saved: {decrypted_filename}"
    except ImportError:
        return False, "PyCryptodome library not installed. Please install: pip install pycryptodome"
    except Exception as e:
        return False, f"Decryption error: {str(e)}"

def get_attendee_id_from_chat(chat_id):
    """
    Get attendee ID (phone number) from chat ID
    """
    url = f"{WHATSAPP_BASE_URL}/chats/{chat_id}"
    headers = {
        'X-API-KEY': WHATSAPP_API_KEY,
        'accept': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Chat Info Status Code: {response.status_code}")
        
        if response.status_code == 200:
            chat = response.json()
            attendee_id = chat.get("attendee_provider_id")
            
            if attendee_id:
                # WhatsApp IDs look like: 917569648853@s.whatsapp.net
                if attendee_id.endswith("@s.whatsapp.net"):
                    print(f"✅ Found attendee ID: {attendee_id}")
                    return attendee_id
                else:
                    print(f"⚠️ attendee_provider_id has unexpected format: {attendee_id}")
                    return None
            else:
                print("❌ No attendee_provider_id found in chat.")
                return None
        else:
            print(f"❌ Failed to fetch chat info: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error fetching chat info: {str(e)}")
        return None

def send_whatsapp_message(chat_id, message_text):
    """
    Send a message to WhatsApp chat
    """
    # First get the attendee ID from the chat ID
    attendee_id = get_attendee_id_from_chat(chat_id)
    if not attendee_id:
        return False, f"Could not get attendee ID for chat_id: {chat_id}"
    
    API_URL = "https://api15.unipile.com:14590/api/v1/chats"
    
    # Construct multipart fields as a list of tuples
    files = [
        ('account_id', (None, 'EDeqAoEmTDmLuWmCbeAyHQ')),             # your WhatsApp account ID
        ('attendees_ids', (None, attendee_id)),                       # recipient (phone number with @s.whatsapp.net)
        ('text', (None, message_text))                               # message text
    ]

    headers = {
        'X-API-KEY': WHATSAPP_API_KEY,
        'accept': 'application/json'
    }

    try:
        response = requests.post(API_URL, headers=headers, files=files)
        print("WhatsApp Message Status Code:", response.status_code)
        
        if response.status_code in [200, 201]:  # Both 200 (OK) and 201 (Created) are success
            try:
                result = response.json()
                print("WhatsApp Message Response:", result)
                return True, "Message sent successfully"
            except Exception as e:
                print("WhatsApp Message Response Text:", response.text)
                return True, "Message sent (response not JSON)"
        else:
            print("WhatsApp Message Error Response:", response.text)
            return False, f"Failed to send message. Status: {response.status_code}"
            
    except Exception as e:
        print(f"Error sending WhatsApp message: {str(e)}")
        return False, f"Error sending message: {str(e)}"

def fetch_latest_whatsapp_file():
    """
    Fetch and decrypt the latest file from WhatsApp messages
    """
    headers = {
        'X-API-KEY': WHATSAPP_API_KEY,
        'accept': 'application/json'
    }
    
    try:
        # Fetch messages globally
        response = requests.get(
            f"{WHATSAPP_BASE_URL}/messages?limit=50",
            headers=headers
        )
        
        if response.status_code != 200:
            return None, f"Failed to fetch messages. Status: {response.status_code}"
        
        data = response.json()
        messages = sorted(data.get("items", []), key=lambda x: x.get("timestamp", ""), reverse=True)
        
        if not messages:
            return None, "No messages found"
        
        # Define supported media types
        msg_types = [
            "documentMessage",
            "imageMessage",
            "videoMessage",
            "audioMessage",
            "stickerMessage"
        ]
        
        # Look for the latest file attachment with media key
        for msg in messages:
            attachments = msg.get("attachments", [])
            if not attachments:
                continue

            original_raw = msg.get("original")
            if not original_raw:
                continue

            try:
                original_json = json.loads(original_raw)
                message_node = original_json.get("message", {})
                found_type = None
                doc_msg = None

                # Find which media type exists
                for mtype in msg_types:
                    if mtype in message_node:
                        doc_msg = message_node[mtype]
                        found_type = mtype
                        break

                if not doc_msg:
                    continue

                url = doc_msg.get("url")
                media_key = doc_msg.get("mediaKey")

                if not url or not media_key:
                    continue

                # Determine file name and extension
                mimetype = attachments[0].get("mimetype")
                ext = get_extension_from_mimetype(mimetype)

                # Prefer fileName from doc_msg if available
                base_name = (
                    doc_msg.get("fileName")
                    or attachments[0].get("file_name")
                    or f"{found_type}"
                )

                base_name = base_name.replace("/", "_").replace("\\", "_")
                file_ts = msg.get("timestamp", "").replace(":", "").replace("-", "")
                file_name = f"{found_type}_{file_ts}{ext}"
                chat_id = msg.get("chat_id")  # Store chat_id for later use
                
                # Download the encrypted file
                file_resp = requests.get(url)
                if file_resp.status_code != 200:
                    continue

                # Save encrypted file to temporary location
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".enc") as tmp_enc_file:
                    tmp_enc_file.write(file_resp.content)
                    enc_file_path = tmp_enc_file.name

                # Decrypt the file
                decrypted_filename = f"decrypted_{file_name}"
                success, decrypt_msg = decrypt_whatsapp_media(enc_file_path, decrypted_filename, media_key, found_type)
                
                # Clean up encrypted file
                try:
                    os.unlink(enc_file_path)
                except:
                    pass

                if success:
                    # Validate the decrypted file (only for PDFs)
                    if decrypted_filename.lower().endswith('.pdf'):
                        is_valid, validation_msg = validate_pdf_file(decrypted_filename)
                        if not is_valid:
                            # Clean up invalid file
                            try:
                                os.unlink(decrypted_filename)
                            except:
                                pass
                            return None, f"Invalid PDF file after decryption: {validation_msg}"
                    
                    # Return chat_id along with file info
                    return decrypted_filename, file_name, chat_id
                else:
                    return None, decrypt_msg, None

            except json.JSONDecodeError:
                continue
            except Exception as e:
                continue
        
        return None, "No document/image/audio/video/sticker found in messages", None
        
    except Exception as e:
        return None, f"Error fetching WhatsApp file: {str(e)}", None

# Streamlit app
st.set_page_config(page_title="Document Extraction Tool", page_icon="📄", layout="wide")

st.title("📄 WhatsApp Document Extraction Tool")
st.markdown("Fetch and extract text from WhatsApp files using Google Gemini AI")

# Xero Token Status
st.sidebar.header("🔐 Xero Authentication")

# Always show current token status
token_manager = XeroTokenManager()
st.sidebar.info(f"**Current Refresh Token:** {token_manager.refresh_token[:30]}...")
if token_manager.access_token:
    st.sidebar.success(f"**Access Token:** {token_manager.access_token[:30]}...")
else:
    st.sidebar.warning("**Access Token:** Not available")

if token_manager.tenant_id:
    st.sidebar.success(f"**Tenant ID:** {token_manager.tenant_id}")
else:
    st.sidebar.warning("**Tenant ID:** Not available")

# Check if token file exists and show its content
try:
    if os.path.exists("refresh_token.json"):
        with open("refresh_token.json", "r") as f:
            file_data = json.load(f)
        file_token = file_data.get("refresh_token", "")
        last_updated = file_data.get("last_updated", "Unknown")
        
        st.sidebar.info(f"**File Token:** {file_token[:30]}...")
        st.sidebar.info(f"**Last Updated:** {last_updated}")
        
        if file_token == token_manager.refresh_token:
            st.sidebar.success("✅ File and memory tokens match")
        else:
            st.sidebar.warning("⚠️ File and memory tokens differ")
    else:
        st.sidebar.warning("📄 No token file found")
except Exception as e:
    st.sidebar.error(f"❌ Error reading token file: {e}")

if st.sidebar.button("🔄 Manual Token Refresh", key="manual_refresh"):
    with st.sidebar.spinner("Refreshing..."):
        token_manager = XeroTokenManager()
        if token_manager.refresh_access_token():
            st.sidebar.success("✅ Tokens refreshed!")
            st.sidebar.info(f"New Refresh Token: {token_manager.refresh_token[:30]}...")
        else:
            st.sidebar.error("❌ Refresh failed!")

if st.sidebar.button("🧪 Test Token Refresh", key="test_refresh"):
    with st.sidebar.spinner("Testing..."):
        if test_token_refresh():
            st.sidebar.success("✅ Token refresh test passed!")
        else:
            st.sidebar.error("❌ Token refresh test failed!")

# WhatsApp fetch section
st.header("📱 Fetch from WhatsApp")

col1, col2 = st.columns([3, 1])

with col1:
    if st.button("📥 Fetch Latest File from WhatsApp", type="primary", use_container_width=True):
        with st.spinner("Fetching latest file from WhatsApp..."):
            file_path, filename, chat_id = fetch_latest_whatsapp_file()
            if file_path:
                st.success(f"✅ File fetched from WhatsApp: {filename}")
                st.session_state.whatsapp_file_path = file_path
                st.session_state.whatsapp_filename = filename
                st.session_state.file_source = "whatsapp"
                st.session_state.chat_id = chat_id  # Store chat_id for later use
                if chat_id:
                    st.info(f"Chat ID: {chat_id}")
            else:
                st.error(f"❌ {filename}")  # filename contains error message here

with col2:
    if st.button("🔄 Retry Fetch", type="secondary"):
        with st.spinner("Retrying fetch and decrypt from WhatsApp..."):
            # Clear previous file
            if hasattr(st.session_state, 'whatsapp_file_path') and st.session_state.whatsapp_file_path:
                try:
                    if os.path.exists(st.session_state.whatsapp_file_path):
                        os.unlink(st.session_state.whatsapp_file_path)
                except:
                    pass
            
            file_path, filename, chat_id = fetch_latest_whatsapp_file()
            if file_path:
                st.success(f"✅ File decrypted from WhatsApp: {filename}")
                st.session_state.whatsapp_file_path = file_path
                st.session_state.whatsapp_filename = filename
                st.session_state.file_source = "whatsapp"
                st.session_state.chat_id = chat_id  # Store chat_id for later use
                if chat_id:
                    st.info(f"Chat ID: {chat_id}")
            else:
                st.error(f"❌ {filename}")  # filename contains error message here

# File processing section
st.header("🔍 Process Document")

# Check if we have a WhatsApp file to process
if hasattr(st.session_state, 'whatsapp_file_path') and st.session_state.whatsapp_file_path:
    file_to_process = st.session_state.whatsapp_file_path
    st.success(f"✅ WhatsApp file decrypted and ready: {st.session_state.whatsapp_filename}")
    
    # Determine MIME type from the original filename (remove 'decrypted_' prefix)
    original_filename = st.session_state.whatsapp_filename
    if original_filename.startswith('decrypted_'):
        original_filename = original_filename[11:]  # Remove 'decrypted_' prefix
    
    file_extension = original_filename.split('.')[-1].lower()
    file_size = os.path.getsize(file_to_process)
    
    mime_types = {
        'pdf': 'application/pdf',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
        'tiff': 'image/tiff'
    }
    mime_type = mime_types.get(file_extension, 'application/octet-stream')
    st.info(f"Original filename: {original_filename}")
    st.info(f"Detected MIME type: {mime_type}")
    st.info(f"File size: {file_size} bytes")
    
    # Extract button
    if st.button("🔍 Extract Content", type="primary", use_container_width=True):
        with st.spinner("Processing document with Gemini AI..."):
            try:
                # Use the already downloaded WhatsApp file
                tmp_file_path = file_to_process
                
                st.info(f"Processing file: {tmp_file_path}")
                
                # Extract content
                result = extract_raw_context_from_file(tmp_file_path, mime_type)
                
                if result:
                    st.success("✅ Extraction completed successfully!")
                    
                    # Process invoice data if document type is invoice/receipt
                    processed_data = None
                    if result.get("document_type", "").lower() in ["invoice", "receipt", "bill"]:
                        with st.spinner("Processing invoice data..."):
                            processed_data = process_invoice_data(result, tmp_file_path, mime_type)
                    
                    # Store processed data in session state
                    if processed_data:
                        st.session_state.processed_data = processed_data
                        st.session_state.xero_data = xero_payload(processed_data)
                        st.session_state.extraction_complete = True
                    else:
                        st.session_state.extraction_complete = False
                        if result.get("document_type", "").lower() in ["invoice", "receipt", "bill"]:
                            st.error("❌ Failed to process invoice data.")
                        else:
                            st.info("ℹ️ Document is not an invoice/receipt. Invoice processing skipped.")
                        
                else:
                    st.error("❌ Failed to extract content. Please check the file and try again.")
                    
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                st.exception(e)

# Display results if extraction is complete
if hasattr(st.session_state, 'extraction_complete') and st.session_state.extraction_complete:
    st.header("📋 Extraction Results")
    
    # Display processed data
    if hasattr(st.session_state, 'processed_data'):
        st.subheader("Processed Invoice Data")
        st.json(st.session_state.processed_data)
    
    # Display Xero payload and API button
    if hasattr(st.session_state, 'xero_data') and st.session_state.xero_data:
        st.subheader("Xero API Payload")
        st.json(st.session_state.xero_data)
        
        # Add button to test Xero authentication
        if st.button("🔑 Test Xero Authentication", type="secondary", key="test_auth"):
            with st.spinner("Testing Xero authentication..."):
                access_token, tenant_id = get_fresh_xero_credentials()
                if access_token and tenant_id:
                    st.success("✅ Xero authentication successful!")
                    st.info(f"Access Token: {access_token[:50]}...")
                    st.info(f"Tenant ID: {tenant_id}")
                else:
                    st.error("❌ Xero authentication failed!")
        
        # Add button to manually refresh tokens
        if st.button("🔄 Refresh Xero Tokens", type="secondary", key="refresh_tokens"):
            with st.spinner("Refreshing Xero tokens..."):
                token_manager = XeroTokenManager()
                if token_manager.refresh_access_token():
                    st.success("✅ Tokens refreshed successfully!")
                    st.info(f"New Access Token: {token_manager.access_token[:50]}...")
                    st.info(f"New Refresh Token: {token_manager.refresh_token[:50]}...")
                else:
                    st.error("❌ Failed to refresh tokens!")
        
        # Add button to send to Xero API
        if st.button("🚀 Send to Xero API", type="primary", key="send_to_xero"):
            with st.spinner("Sending invoice to Xero..."):
                api_result = send_to_xero_api(st.session_state.xero_data)
                
                if api_result["success"]:
                    st.success("✅ Invoice successfully sent to Xero!")
                    st.subheader("Xero API Response")
                    st.json(api_result["data"])
                    
                    # Send confirmation message to WhatsApp
                    if hasattr(st.session_state, 'chat_id') and st.session_state.chat_id:
                        with st.spinner("Sending confirmation to WhatsApp..."):
                            # Create confirmation message with invoice details
                            invoice_data = st.session_state.processed_data
                            confirmation_message = f"""✅ Invoice processed and stored in Xero successfully!

📄 Invoice Details:
• Company: {invoice_data.get('CompanyName', 'N/A')}
• Invoice Number: {invoice_data.get('InvoiceNumber', 'N/A')}
• Date: {invoice_data.get('InvoiceDate', 'N/A')}
• Total Amount: {invoice_data.get('GrandTotalExtracted', 'N/A')} KWD

The invoice has been automatically processed and is now available in your Xero account."""
                            
                            success, msg_result = send_whatsapp_message(st.session_state.chat_id, confirmation_message)
                            if success:
                                st.success("✅ Confirmation sent to WhatsApp!")
                            else:
                                st.warning(f"⚠️ Could not send WhatsApp confirmation: {msg_result}")
                    else:
                        st.info("ℹ️ No WhatsApp chat ID available for confirmation message")
                        
                else:
                    st.error(f"❌ Failed to send to Xero: {api_result.get('error', 'Unknown error')}")
                    if api_result.get("text"):
                        st.text("Response text:")
                        st.code(api_result["text"])
                    
                    # Send error message to WhatsApp if available
                    if hasattr(st.session_state, 'chat_id') and st.session_state.chat_id:
                        with st.spinner("Sending error notification to WhatsApp..."):
                            error_message = f"""❌ Invoice processing failed

The invoice could not be processed and stored in Xero. Please check the file and try again.

Error: {api_result.get('error', 'Unknown error')}"""
                            
                            success, msg_result = send_whatsapp_message(st.session_state.chat_id, error_message)
                            if success:
                                st.info("ℹ️ Error notification sent to WhatsApp")
                            else:
                                st.warning(f"⚠️ Could not send WhatsApp notification: {msg_result}")

# Cleanup WhatsApp files when session ends
def cleanup_whatsapp_files():
    if hasattr(st.session_state, 'whatsapp_file_path') and st.session_state.whatsapp_file_path:
        try:
            if os.path.exists(st.session_state.whatsapp_file_path):
                os.unlink(st.session_state.whatsapp_file_path)
                print(f"Cleaned up decrypted WhatsApp file: {st.session_state.whatsapp_file_path}")
        except Exception as e:
            print(f"Error cleaning up WhatsApp file: {e}")

# Register cleanup function
if 'cleanup_registered' not in st.session_state:
    st.session_state.cleanup_registered = True
    # Note: Streamlit doesn't have a built-in session end callback
    # Files will be cleaned up when the app restarts or manually

# Instructions
with st.expander("ℹ️ How to use"):
    st.markdown("""
    ### Instructions:
    1. **Fetch from WhatsApp**: Click 'Fetch Latest File from WhatsApp' to get and decrypt the most recent file from your WhatsApp messages
    2. **Click Extract**: Press the 'Extract Content' button to process the decrypted document
    3. **View results**: The processed invoice data will be displayed directly:
       - **Company Name**: Name of the company issuing the invoice
       - **Customer Name**: Name of the customer
       - **Invoice Number**: Unique invoice identifier
       - **Invoice Date**: Date of the invoice
       - **Grand Total**: Total amount with Kuwaiti Dinar formatting
       - **Invoice Items**: List of items with description, quantity, and amount
    
    ### Supported File Types:
    - **PDF**: Documents, forms, reports
    - **Images**: PNG, JPG, JPEG, GIF, BMP, TIFF
    
    ### What gets extracted:
    - **For invoices/receipts**: Company name, invoice number, date, items, and total with Kuwaiti Dinar formatting
    - Document type identification (for processing logic)
    
    ### Kuwaiti Dinar Formatting:
    - Comma-separated amounts (e.g., "4,90" → "4.900")
    - Split numbers (e.g., "24 | 500" → "24.500")
    - All amounts formatted with 3-digit fils
    
    ### WhatsApp Integration:
    - Automatically fetches and decrypts the latest file attachment from your WhatsApp messages
    - Handles WhatsApp's encrypted document format
    - Supports document messages (PDFs, images, etc.)
    - Files are decrypted, validated, and processed
    - Requires PyCryptodome library for decryption: `pip install pycryptodome`
    
    ### Xero Authentication:
    - Uses refresh token-based authentication (no browser automation)
    - Tokens are automatically refreshed when expired
    - Refresh tokens are saved to `xero_refresh_token.txt` for persistence
    - Manual token refresh available in sidebar
    - Automatic retry on 401 authentication errors
    """)

# Footer
st.markdown("---")
st.markdown("Powered by Google Gemini AI | Built with Streamlit") 
