# Multi-Language Support Implementation

## Overview
The Amazon Tracker Bot now supports **English** and **Arabic** with full localization of:
- Bot messages and prompts
- Product information (names, descriptions, specs)
- Error messages and confirmations
- Help text and instructions

## Features Implemented

### 1. **Language Selection** 🌐
- Users can switch languages using the **🌐 Language** button
- Default language: **English**
- Available languages: **English** (🇬🇧) and **العربية** (🇸🇦)
- Language preference is remembered during the session

### 2. **Product Information in Multiple Languages**
When a user adds a product:
- **Product name** - Fetched in the selected language
- **Product description** - Extracted from the product page (up to 500 chars)
- **Product specifications** - Key specs from the product details table
- **Price** - Always in EGP (Egyptian Pound)

### 3. **Full Bot Localization**
All bot messages are translated:
- ✅ Help and command descriptions
- ✅ Success/error messages
- ✅ Prompts and confirmations
- ✅ Menu labels and instructions
- ✅ Price update notifications

### 4. **Languages Supported**

#### English (en)
- Default language
- Full English product descriptions and specifications
- English command help text

#### العربية (ar)
- Complete Arabic translations
- Arabic product descriptions and specs
- Arabic command help text and prompts

## Usage

### Switching Languages
1. Tap the **🌐 Language** button in the main menu
2. Choose **🇬🇧 English** or **🇸🇦 العربية**
3. All bot messages will update to the selected language

### Adding Products in Different Languages
- The bot fetches product information in your selected language
- Product names, descriptions, and specifications match your language preference
- Prices remain consistent (EGP)

## Technical Implementation

### Files Modified

#### bot.py
- **Translation Dictionary**: Stores all text in both languages
- **build_help_message()**: Now accepts `lang` parameter
- **build_menu_markup()**: Now accepts `lang` parameter
- **Language handler**: Manages language switching
- **get_text()**: Helper function for translated text

#### scraper.py
- **fetch_product()**: Accepts `lang` parameter
- **_extract_name()**: Fetches name in selected language
- **_extract_description()**: Extracts product description
- **_extract_specs()**: Extracts product specifications
- Both functions support Arabic and English content

#### database.py
- No changes needed (language is passed at display time)

### Session Management
- Language preference stored in `context.user_data["language"]`
- Persists during the session
- Returns to default (English) on new session

## Example Translations

### Help Command
**English**: "🤖 *Amazon Price Tracker*\n\nTrack product prices..."
**Arabic**: "🤖 *تتبع أسعار أمازون*\n\nتتبع أسعار المنتجات..."

### Add Product Confirmation
**English**: "✅ *Successfully Added!*"
**Arabic**: "✅ *تمت الإضافة بنجاح!*"

## Adding More Languages

To add support for additional languages:

1. **Add to TRANSLATIONS dictionary**:
   ```python
   TRANSLATIONS = {
       "en": { ... },
       "ar": { ... },
       "fr": {  # New language
           "help_title": "...",
           # ... all keys
       }
   }
   ```

2. **Update language selection UI**:
   ```python
   lang_keyboard = [
       [
           InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
           InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
           InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr"),  # Add here
       ],
   ]
   ```

3. **Handle in callback handler**:
   - Already supports dynamic language codes via `action.startswith("lang_")`

## Language Fetching Strategy

The bot fetches content in the user's selected language by:

1. **Product Names**: Amazon pages display content based on language preference
2. **Descriptions**: Extracted from feature bullet points (supports RTL for Arabic)
3. **Specifications**: Extracted from the product details table (language-neutral format)
4. **Prices**: Always in local currency (EGP)

## Notes

- Price notifications include all translated text
- Product list displays in user's selected language
- All error messages are localized
- Arabic text displays correctly with RTL (Right-to-Left) support in Telegram

## Future Enhancements

Potential language-related improvements:
- [ ] Persist language preference in database (across sessions)
- [ ] Auto-detect device language preference
- [ ] Add more regional Amazon sites (Amazon.sa, Amazon.ae)
- [ ] Translate product reviews or ratings
- [ ] Multi-language price history tracking
