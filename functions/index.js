const functions = require('firebase-functions');
const axios = require('axios');

// You should store this in 
const API_KEY = functions.config().fastapi.key;;
const API_URL = functions.config().fastapi.cleanendpoint;

exports.cleanTokens = functions.pubsub
    .schedule('every 1 minutes')
    .timeZone('UTC')
    .onRun(async (context) => {
        try {
            const response = await axios({
                method: 'put',
                url: API_URL,
                headers: {
                    'Authorization': `Bearer ${API_KEY}`,
                    'Content-Type': 'application/json'
                }
            });

            console.log('FastAPI response:', response.data);
            return null;
        } catch (error) {
            console.error('Error calling FastAPI:', error.response?.data || error.message);
            return null;
        }
    });