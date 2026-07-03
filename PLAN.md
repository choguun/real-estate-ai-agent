**Concrete Implementation Plan**  
**Month 1 (Week 1–4) – MVP Development**

### Week 1: Foundation Setup

**Goal**: Set up a clean, scalable project structure with authentication and database ready.

**Tasks**:

1. **Create GitHub Repository**
   - Create a new repository on GitHub named `real-estate-ai-agent`
   - Add `.gitignore` for Python, Node.js, and environment files
   - Initialize with `README.md` describing the project

2. **Frontend Setup (Next.js 15)**
   - Run command:
     ```bash
     npx create-next-app@latest . --yes
     ```
   - Install required packages:
     ```bash
     npm install tailwindcss @shadcn/ui lucide-react
     npm install @supabase/supabase-js
     ```
   - Set up Tailwind CSS and shadcn/ui components

3. **Backend Setup (FastAPI)**
   - Create a `backend/` folder
   - Initialize FastAPI project:
     ```bash
     cd backend
     python -m venv venv
     pip install fastapi uvicorn python-dotenv
     ```
   - Create basic structure:
     - `main.py`
     - `routers/`
     - `models/`
     - `services/`

4. **Supabase Setup**
   - Create a new Supabase project
   - Set up tables:
     - `users`
     - `properties` (for listings)
     - `leads`
   - Enable Row Level Security (RLS)
   - Get `SUPABASE_URL` and `SUPABASE_ANON_KEY`

5. **Environment Configuration**
   - Create `.env` files for both frontend and backend
   - Set up environment variables for Supabase, LINE, and AI keys

**Deliverables by End of Week 1**:
- GitHub repository created with proper structure
- Next.js frontend running locally with Tailwind
- FastAPI backend running with basic `/health` endpoint
- Supabase connected to both frontend and backend
- Basic authentication flow (Sign up / Login) working

**Estimated Time**: 8–10 days (including setup and testing)

---

### Week 2: LINE Integration

**Goal**: Connect the application with LINE Official Account so it can receive and send messages.

**Tasks**:

1. **Create LINE Official Account**
   - Go to LINE Developers Console
   - Create a new Messaging API channel
   - Get **Channel Access Token** and **Channel Secret**

2. **Set Up LINE Webhook**
   - In `backend/routers/`, create `line_router.py`
   - Create webhook endpoint:
     ```python
     @router.post("/webhook")
     async def line_webhook(request: Request):
         # Verify signature
         # Parse events
         # Handle message events
     ```

3. **Implement Message Handling**
   - Create service to receive text messages from users
   - Store incoming messages in Supabase `leads` or `messages` table
   - Create function to reply to users using LINE API

4. **Test LINE Connection**
   - Use LINE Bot Tester or add your LINE account as a friend
   - Test sending and receiving messages
   - Log all incoming messages in the database

5. **Basic Dashboard Display**
   - In Next.js frontend, create a simple page that shows recent messages from LINE
   - Connect frontend to backend API to fetch messages

**Deliverables by End of Week 2**:
- LINE Webhook is working and receiving messages
- Backend can reply to LINE messages
- Messages are stored in Supabase
- Simple dashboard page showing received LINE messages

**Estimated Time**: 8–9 days

---

### Week 3: AI Listing Generator (Part 1)

**Goal**: Build the core AI feature that generates real estate listing descriptions.

**Tasks**:

1. **Set Up AI Integration**
   - Choose AI model (Recommended: **Claude 3.5 Sonnet** or **Gemini 2.0**)
   - Install required packages:
     ```bash
     pip install anthropic google-generativeai langchain
     ```
   - Create `services/ai_service.py`

2. **Design Prompt Template**
   - Create effective prompts for generating:
     - Property description
     - Key features
     - SEO-friendly title
     - Hashtags (for Facebook)
   - Store prompts in a structured way (can start with simple string templates)

3. **Create Backend API Endpoint**
   - Build endpoint: `POST /api/generate-listing`
   - Accept input: property details + images (image URLs or descriptions)
   - Return generated listing text in Thai

4. **Frontend Form**
   - Create a form in Next.js where users can:
     - Upload property photos
     - Fill in basic details (price, size, location, bedrooms, etc.)
     - Submit to generate listing

5. **Basic Output Display**
   - Show generated listing text on the screen
   - Allow users to copy the result

**Deliverables by End of Week 3**:
- Working AI Listing Generator API
- Frontend form that accepts property information
- Generated listing text displayed to the user
- Basic prompt engineering completed

**Estimated Time**: 9 days

---

### Week 4: AI Listing Generator (Part 2) + Testing

**Goal**: Improve the AI output quality and complete end-to-end testing of the feature.

**Tasks**:

1. **Improve Prompt Engineering**
   - Test and refine prompts with real Thai real estate data
   - Add support for different property types (Condo, House, Land, Townhouse)
   - Make output suitable for DDProperty, Livinginsider, and Facebook

2. **Add Image Analysis (Optional but Recommended)**
   - Use AI vision capability (Claude or Gemini) to analyze uploaded property photos
   - Extract features from images (e.g., modern kitchen, sea view)

3. **Enhance User Experience**
   - Allow users to edit the generated text before saving
   - Add option to generate multiple versions
   - Save generated listings to Supabase

4. **End-to-End Testing**
   - Test full flow:
     1. User uploads property info
     2. AI generates listing
     3. User can edit and save
     4. Listing appears in dashboard
   - Test with 5–10 real property examples

5. **Bug Fixing & Optimization**
   - Fix issues found during testing
   - Optimize API response time
   - Add loading states in frontend

**Deliverables by End of Week 4**:
- Improved and reliable AI Listing Generator
- Full working flow from input → generation → saving
- Tested with real Thai property data
- Clean and user-friendly interface

**Estimated Time**: 9–10 days

---

### Summary – Month 1 Target

| Week | Focus Area                    | Main Deliverable                     | Readiness |
|------|-------------------------------|--------------------------------------|---------|
| 1    | Foundation Setup              | Project structure + Supabase ready   | High    |
| 2    | LINE Integration              | Send & receive LINE messages         | High    |
| 3    | AI Listing Generator (Part 1) | Basic AI listing generation          | Medium  |
| 4    | AI Listing Generator (Part 2) | Polished & tested listing feature    | High    |

**End of Month 1 Goal**:  
Have a working system where a real estate agent can connect their LINE, input property details, and generate a ready-to-post listing using AI.