-- TeamLogicHandler (Server Script within ServerScriptService)

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")

-- Wait for the event to exist
local StartTeamLogicEvent = ReplicatedStorage:WaitForChild("StartTeamLogic")

-- Ensure a RemoteEvent exists for receiving personality quiz responses
local ReceivePersonalityQuiz = ReplicatedStorage:FindFirstChild("ReceivePersonalityQuiz") or Instance.new("RemoteEvent")
ReceivePersonalityQuiz.Name = "ReceivePersonalityQuiz"
ReceivePersonalityQuiz.Parent = ReplicatedStorage

-- List of possible teams
local TEAM_POOL = {"EMBER", "TERRA", "VEIL", "AERIAL", "HALO", "FLUX", "NOVA", "TEMPO"}

-- Flask API endpoint
local API_URL = "https://roblox-gemini-bridge-flask.fly.dev/team_quiz"

-- Function to send randomly chosen teams to the Flask API
local function sendTeamsToServer()
	local playerList = Players:GetPlayers()
	local playerCount = #playerList

	print("StartTeamLogic Event Triggered! Player count:", playerCount)

	-- Determine the number of teams based on player count
	local numTeams
	if playerCount >= 6 and playerCount <= 10 then
		numTeams = 2
	elseif playerCount >= 11 and playerCount <= 15 then
		numTeams = 3
	elseif playerCount > 15 then
		numTeams = 4
	else
		numTeams = 2 -- Default to 2 teams if less than 6 players
	end

	-- Select unique random teams
	local selectedTeams = {}
	while #selectedTeams < numTeams do
		local randomTeam = TEAM_POOL[math.random(1, #TEAM_POOL)]
		if not table.find(selectedTeams, randomTeam) then
			table.insert(selectedTeams, randomTeam)
		end
	end

	-- Get the Game ID (to ensure the response comes back to the correct server)
	local currentGameId = "UNKNOWN_GAME_ID"
	for _, player in ipairs(playerList) do
		local joinData = player:GetJoinData()
		if joinData and joinData.TeleportData and joinData.TeleportData.gameId then
			currentGameId = joinData.TeleportData.gameId
			break
		end
	end

	-- Print the selected teams
	print("Selected Teams:", table.concat(selectedTeams, ", "))
	print("Sending data to API with Game ID:", currentGameId)

	-- Create JSON data to send
	local teamData = {
		game_id = currentGameId, -- Include Game ID for response tracking
		teams = selectedTeams
	}
	local jsonData = HttpService:JSONEncode(teamData)

	-- Send HTTP POST request to the Flask API
	local success, response = pcall(function()
		return HttpService:PostAsync(API_URL, jsonData, Enum.HttpContentType.ApplicationJson, false)
	end)

	-- Handle response
	if success then
		print("Successfully sent teams to Flask API. Response received.")

		-- Decode the response
		local decodedResponse = HttpService:JSONDecode(response)

		-- Check if quiz questions exist in the response
		if decodedResponse and decodedResponse.quiz_questions then
			print("Received Quiz Questions:")

			-- Loop through and print each question
			for i, question in ipairs(decodedResponse.quiz_questions) do
				print(i .. ". " .. question)
			end

			-- Send quiz questions to clients
			ReceivePersonalityQuiz:FireAllClients(decodedResponse.quiz_questions)
		else
			warn("Quiz questions not found in the API response.")
		end
	else
		warn("Failed to send teams to Flask API:", response)
	end
end

-- Connect the function to the event
StartTeamLogicEvent.Event:Connect(sendTeamsToServer)
