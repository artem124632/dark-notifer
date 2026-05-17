-- Клиентский логгер ATLAS для Roblox
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")

local LicenseKey = "ATLAS-FREE-KEY" -- Твой дефолтный валидный ключ
local ServerUrl = "http://127.0.0.1:8000/api/report_server"

print("[ATLAS] Подключение к локальной веб-панели...")

task.spawn(function()
    while task.wait(10) do -- Отправка логов каждые 10 секунд
        local success, err = pcall(function()
            local payload = {
                key = LicenseKey,
                job_id = game.JobId ~= "" and game.JobId or "LOCAL_TEST_SERVER_ID",
                players = #Players:GetPlayers(),
                max_players = game.MaxPlayers,
                region = "RU-OLED"
            }
            
            local jsonData = HttpService:JSONEncode(payload)
            local response = syn and syn.request or http and http.request or request
            
            if response then
                response({
                    Url = ServerUrl,
                    Method = "POST",
                    Headers = { ["Content-Type"] = "application/json" },
                    Body = jsonData
                })
            else
                -- Для обычного Studio теста
                HttpService:PostAsync(ServerUrl, jsonData, Enum.HttpContentType.ApplicationJson)
            end
        end)
        if not success then
            warn("[ATLAS] Ошибка отправки данных на панель: " .. tostring(err))
        end
    end
end)