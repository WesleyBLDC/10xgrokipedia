import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import TopicPage from "./pages/TopicPage";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/page/:topic" element={<TopicPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
