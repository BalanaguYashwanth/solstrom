const API_URL = process.env.REACT_APP_API_URL;

export const sendMessage = async (message: string, user?: any) => {
  try {
    const body: any = { message };
    if (user) body.user = user;
    const response = await fetch(`${API_URL}/agent/conversation`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error("Network response was not ok");
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error sending message:", error);
    throw error;
  }
};
