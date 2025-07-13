import React, { useEffect, useRef, useState } from "react";
import { TypingLoader } from "./components/TypingLoader/TypingLoader";
import Popup from "./components/Popup/Popup";
import { sendMessage as sendMessageApi } from "./common/api.services";
import { EXAMPLE_QUERIES } from "./common/queries.constants";
import { Message, ProjectAgentResponse } from "./common/types";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import "./App.scss";

const App: React.FC = () => {
  const { connection } = useConnection();
  const [solAmount, setSolAmount] = useState(0.5);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showLimitPopup, setShowLimitPopup] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    if (messages.length === 0) {
      const timeout = setTimeout(() => {
        const welcomeMessage: Message = {
          text: "👋 Welcome, How can I help your sol projects",
          sender: "bot"
        };
        setMessages([welcomeMessage]);
      }, 600);
      return () => clearTimeout(timeout);
    }
  }, []);


  const sendMessage = async (message: string) => {
    return await sendMessageApi(message);
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    if (messages.length >= 5) {
      setShowLimitPopup(true);
      return;
    }

    const newMessage: Message = { text: input.trim(), sender: "user" };
    setMessages((prev) => [...prev, newMessage]);
    const currentInput = input.trim();
    setInput("");
    setIsLoading(true);

    try {
      let apiResponse;
      apiResponse = await sendMessage(currentInput);
      if (apiResponse?.limitReached) {
        setShowLimitPopup(true);
        if (apiResponse?.conversation?.response) {
          const botMessage: Message = {
            text: apiResponse.conversation.response.join(" "),
            sender: "bot"
          };
          setMessages((prev) => [...prev, botMessage]);
        }
        return;
      }

      if (apiResponse?.conversation) {
        const { response, relevant_projects, sources } = apiResponse.conversation;
        const botMessage: Message = {
          text: "",
          sender: "bot",
          projectData: {
            points: Array.isArray(response) ? response : [response],
            is_greeting: false,
            exists_in_data: false,
            exists_elsewhere: false,
            relevant_projects: relevant_projects || [],
            sources: sources || [{ source_name: '', source_url: '' }],
          }
        };
        setMessages((prev) => [...prev, botMessage]);

      } else {
        setMessages((prev) => [
          ...prev,
          { text: "No response received", sender: "bot" },
        ]);
      }
    } catch (error) {
      console.error("Error:", error);
      setMessages((prev) => [
        ...prev,
        { text: "Sorry, something went wrong. Please try again.", sender: "bot" },
      ]);
    } finally {
      setIsLoading(false);
    }
  };


  const { publicKey, sendTransaction } = useWallet();


  const handleAmount = (amount: string | number) => {
    setSolAmount(Number(amount))
  }

  const handlePay = async () => {


    if (solAmount < 0.5 || solAmount > 20) {
      alert("Amount must be between 0.5 and 20 SOL");
      return;
    }

    if (!publicKey) {
      alert("Wallet is not connected properly, please reconnect it again");
      return;
    }

    try {
      const LAMPORTS_PER_SOL = 1000000000
      const recipientPubKey = new PublicKey('DTrXdM5a3X4dcSZRGF18Q1f1kLa8eoYThiFeV4uu5nwQ')
      const transaction = new Transaction();
      const sendSolInstruction = SystemProgram.transfer({
        fromPubkey: publicKey,
        toPubkey: recipientPubKey,
        lamports: solAmount * LAMPORTS_PER_SOL,
      });

      transaction.add(sendSolInstruction);

      const signature = await sendTransaction(transaction, connection);
      console.log(`Transaction signature: ${signature}`);

      alert("Payment successful!");
      setShowLimitPopup(false);
    } catch (error) {
      console.error("Payment failed:", error);
      alert("Transaction failed. Try again.");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderProjectResponse = (data: ProjectAgentResponse) => {
    if (!data || !Array.isArray(data.points)) {
      return "Invalid response format.";
    }
    if (data.is_greeting) {
      return (
        <div className="greetingResponse">
          {data.points.map((point, i) => (
            <div key={i} className="welcomePoint">{point}</div>
          ))}
        </div>
      );
    }

    return (
      <div className="projectResponse">
        {data.points.map((point, i) => (
          <div key={i} className="responsePoint">{point}</div>
        ))}

        {data.relevant_projects && data.relevant_projects.length > 0 && (
          <div className="metaInfo">
            <div className="section">
              <h4>Related Projects:</h4>
              <ul>
                {data.relevant_projects.map((project, i) => (
                  <li key={i}>{project}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {data.sources && data.sources.length > 0 && (data.sources[0]?.source_name as any) && (
          <div className="section">
            <h4>Sources:</h4>
            <ul className="sourcesList">
              {data.sources.map((source, i) => {
                const sourceName = typeof source === 'object' ? source.source_name : source;
                const sourceUrl = typeof source === 'object' ? source.source_url : '';

                return (
                  <li key={i}>
                    {sourceUrl ? (
                      <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                        {sourceName}
                      </a>
                    ) : (
                      sourceName
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={'chatWrapper'}>
      <div className="messagesWrapper">
        {messages.length === 1 && (
          <div className="placeholder">
            <div>Try one of these examples:</div>
            <ul>
              {EXAMPLE_QUERIES.map((example, idx) => (
                <li
                  key={idx}
                  onClick={() => setInput(example)}
                >
                  {example}
                </li>
              ))}
            </ul>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={msg.sender === "user" ? "userMessage" : "botMessage"}
          >
            {msg.projectData
              ? renderProjectResponse(msg.projectData)
              : msg.text}
          </div>
        ))}

        {isLoading && (
          <div className="botMessage">
            <TypingLoader />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="wallet-container">
        <div className="wallet-button-container">
          <WalletMultiButton className="wallet-button" />
        </div>
      </div>

      <div className="inputBox">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe more about your project to brainstorm or validate etc"
          rows={1}
          className="textarea-input"
          disabled={isLoading}
        />
        <button onClick={handleSend} disabled={isLoading || !input.trim()}>↩</button>
      </div>

      <Popup
        open={showLimitPopup}
        heading="Worth fee"
        message="We are checking is it worth to pay ?"
        showSolanaPay={true}
        onClose={() => setShowLimitPopup(false)}
        handleAmount={handleAmount}
        actions={<button onClick={handlePay}>Pay</button>}
      />
    </div>
  );
};

export default App;